#include "CorridorKeyPlugin.h"
#include "CorridorKeyProcessor.h"

#include <thread>
#include <chrono>
#include <cstdlib>

namespace corridorkey {

// --- Plugin Factory ---

void CorridorKeyPluginFactory::describe(OFX::ImageEffectDescriptor& desc)
{
    desc.setLabel("CorridorKey");
    desc.setPluginGrouping("Corridor Digital");
    desc.setPluginDescription(
        "AI-powered green screen keyer by Corridor Digital. "
        "Produces physically accurate foreground color unmixing with clean linear alpha channels."
    );

    // Supported contexts
    desc.addSupportedContext(OFX::eContextFilter);
    desc.addSupportedContext(OFX::eContextGeneral);

    // Supported pixel depths
    desc.addSupportedBitDepth(OFX::eBitDepthFloat);

    // Plugin properties
    desc.setSingleInstance(false);
    desc.setHostFrameThreading(false);
    desc.setSupportsMultiResolution(true);
    desc.setSupportsTiles(false);  // Need full frame for inference
    desc.setTemporalClipAccess(false);
    desc.setRenderTwiceAlways(false);
    desc.setSupportsMultipleClipPARs(false);
    desc.setSupportsMultipleClipDepths(false);

    // We handle our own threading via the backend process
    desc.setRenderThreadSafety(OFX::eRenderInstanceSafe);
}

void CorridorKeyPluginFactory::describeInContext(
    OFX::ImageEffectDescriptor& desc, OFX::ContextEnum context)
{
    // Source clip (required)
    OFX::ClipDescriptor* srcClip = desc.defineClip(kOfxImageEffectSimpleSourceClipName);
    srcClip->setLabel("Source");
    srcClip->addSupportedComponent(OFX::ePixelComponentRGBA);
    srcClip->addSupportedComponent(OFX::ePixelComponentRGB);
    srcClip->setTemporalClipAccess(false);
    srcClip->setSupportsTiles(false);
    srcClip->setIsMask(false);

    // Alpha hint clip (optional)
    OFX::ClipDescriptor* alphaHintClip = desc.defineClip(kClipAlphaHint);
    alphaHintClip->setLabel("Alpha Hint");
    alphaHintClip->addSupportedComponent(OFX::ePixelComponentAlpha);
    alphaHintClip->addSupportedComponent(OFX::ePixelComponentRGBA);
    alphaHintClip->setTemporalClipAccess(false);
    alphaHintClip->setSupportsTiles(false);
    alphaHintClip->setIsMask(true);
    alphaHintClip->setOptional(true);

    // Output clip
    OFX::ClipDescriptor* dstClip = desc.defineClip(kOfxImageEffectOutputClipName);
    dstClip->addSupportedComponent(OFX::ePixelComponentRGBA);
    dstClip->setSupportsTiles(false);

    // --- Parameters ---

    OFX::PageParamDescriptor* page = desc.definePageParam("Controls");

    // Mode
    {
        OFX::ChoiceParamDescriptor* param = desc.defineChoiceParam(kParamMode);
        param->setLabel("Mode");
        param->setHint("Alpha hint source: Auto uses BiRefNet, External uses the AlphaHint input clip");
        param->appendOption(kModeAuto);
        param->appendOption(kModeExternal);
        param->setDefault(0);
        if (page) page->addChild(*param);
    }

    // BiRefNet Model
    {
        OFX::ChoiceParamDescriptor* param = desc.defineChoiceParam(kParamBiRefNetModel);
        param->setLabel("BiRefNet Model");
        param->setHint("BiRefNet model variant for automatic alpha hint generation");
        param->appendOption(kBiRefNetGeneral);
        param->appendOption(kBiRefNetPortrait);
        param->appendOption(kBiRefNetMatting);
        param->setDefault(0);
        if (page) page->addChild(*param);
    }

    // Input Colorspace
    {
        OFX::ChoiceParamDescriptor* param = desc.defineChoiceParam(kParamInputColorspace);
        param->setLabel("Input Colorspace");
        param->setHint("Colorspace of the source footage");
        param->appendOption(kColorspaceSRGB);
        param->appendOption(kColorspaceLinear);
        param->setDefault(0);
        if (page) page->addChild(*param);
    }

    // Despill Strength
    {
        OFX::DoubleParamDescriptor* param = desc.defineDoubleParam(kParamDespillStrength);
        param->setLabel("Despill Strength");
        param->setHint("Green spill removal intensity");
        param->setRange(0.0, 10.0);
        param->setDisplayRange(0.0, 5.0);
        param->setDefault(1.0);
        if (page) page->addChild(*param);
    }

    // Auto Despeckle
    {
        OFX::BooleanParamDescriptor* param = desc.defineBooleanParam(kParamAutoDespeckle);
        param->setLabel("Auto Despeckle");
        param->setHint("Remove small isolated alpha artifacts");
        param->setDefault(true);
        if (page) page->addChild(*param);
    }

    // Despeckle Size
    {
        OFX::IntParamDescriptor* param = desc.defineIntParam(kParamDespeckleSize);
        param->setLabel("Despeckle Size");
        param->setHint("Minimum pixel area threshold for despeckle");
        param->setRange(1, 10000);
        param->setDisplayRange(10, 2000);
        param->setDefault(400);
        if (page) page->addChild(*param);
    }

    // Refiner Strength
    {
        OFX::DoubleParamDescriptor* param = desc.defineDoubleParam(kParamRefinerStrength);
        param->setLabel("Refiner Strength");
        param->setHint("CNN refiner multiplier");
        param->setRange(0.0, 5.0);
        param->setDisplayRange(0.0, 2.0);
        param->setDefault(1.0);
        if (page) page->addChild(*param);
    }

    // Output Mode
    {
        OFX::ChoiceParamDescriptor* param = desc.defineChoiceParam(kParamOutputMode);
        param->setLabel("Output Mode");
        param->setHint("Select which output to pass downstream");
        param->appendOption(kOutputProcessed);
        param->appendOption(kOutputMatte);
        param->appendOption(kOutputForeground);
        param->appendOption(kOutputComposite);
        param->setDefault(0);
        if (page) page->addChild(*param);
    }
}

OFX::ImageEffect* CorridorKeyPluginFactory::createInstance(
    OfxImageEffectHandle handle, OFX::ContextEnum /*context*/)
{
    return new CorridorKeyPlugin(handle);
}

// --- Plugin Instance ---

CorridorKeyPlugin::CorridorKeyPlugin(OfxImageEffectHandle handle)
    : OFX::ImageEffect(handle)
    , m_ipc(std::make_unique<IPCClient>())
{
    m_srcClip = fetchClip(kOfxImageEffectSimpleSourceClipName);
    m_alphaHintClip = fetchClip(kClipAlphaHint);
    m_dstClip = fetchClip(kOfxImageEffectOutputClipName);

    m_mode = fetchChoiceParam(kParamMode);
    m_birefnetModel = fetchChoiceParam(kParamBiRefNetModel);
    m_inputColorspace = fetchChoiceParam(kParamInputColorspace);
    m_despillStrength = fetchDoubleParam(kParamDespillStrength);
    m_autoDespeckle = fetchBooleanParam(kParamAutoDespeckle);
    m_despeckleSize = fetchIntParam(kParamDespeckleSize);
    m_refinerStrength = fetchDoubleParam(kParamRefinerStrength);
    m_outputMode = fetchChoiceParam(kParamOutputMode);
}

CorridorKeyPlugin::~CorridorKeyPlugin()
{
    if (m_connected) {
        m_ipc->shutdown();
        m_ipc->disconnect();
    }
}

void CorridorKeyPlugin::render(const OFX::RenderArguments& args)
{
    // Fetch images
    std::unique_ptr<OFX::Image> dstImg(m_dstClip->fetchImage(args.time));
    std::unique_ptr<OFX::Image> srcImg(m_srcClip->fetchImage(args.time));
    if (!dstImg || !srcImg) {
        OFX::throwSuiteStatusException(kOfxStatFailed);
        return;
    }

    OfxRectI renderWindow = args.renderWindow;

    // Check bit depth — need float32 for inference
    OFX::BitDepthEnum dstBitDepth = dstImg->getPixelDepth();
    if (dstBitDepth != OFX::eBitDepthFloat) {
        setPersistentMessage(OFX::Message::eMessageError, "",
            "CorridorKey requires 32-bit float processing. "
            "Set project to float in Project Settings > Color Management.");
        CorridorKeyProcessor::copyImage(srcImg.get(), dstImg.get(), renderWindow);
        return;
    }

    // Optionally fetch alpha hint
    std::unique_ptr<OFX::Image> alphaHintImg;
    int modeVal = 0;
    m_mode->getValueAtTime(args.time, modeVal);
    bool hasAlphaHint = false;
    if (modeVal == 1 && m_alphaHintClip && m_alphaHintClip->isConnected()) {
        alphaHintImg.reset(m_alphaHintClip->fetchImage(args.time));
        hasAlphaHint = (alphaHintImg != nullptr);
    }

    // Get render window dimensions
    int width = renderWindow.x2 - renderWindow.x1;
    int height = renderWindow.y2 - renderWindow.y1;

    // Ensure backend connection (non-blocking: auto-launch happens in background)
    if (!ensureConnected()) {
        // Fallback: pass through source
        CorridorKeyProcessor::copyImage(srcImg.get(), dstImg.get(), renderWindow);
        return;
    }

    // Build parameters
    ProcessFrameParams params = buildParams(args.time);
    params.width = width;
    params.height = height;
    params.has_alpha_hint = hasAlphaHint;

    // Process via backend
    CorridorKeyProcessor processor(*this);
    processor.setImages(srcImg.get(), dstImg.get(), alphaHintImg.get());
    processor.setRenderWindow(renderWindow);
    processor.setParams(params);
    processor.setIPCClient(m_ipc.get());
    processor.process();

    // If processing failed, reset connection so we reconnect next frame
    if (!processor.succeeded()) {
        std::lock_guard<std::mutex> lock(m_ipcMutex);
        m_ipc->disconnect();
        m_connected = false;
    }
}

bool CorridorKeyPlugin::getRegionOfDefinition(
    const OFX::RegionOfDefinitionArguments& args, OfxRectD& rod)
{
    // Output ROD matches source
    if (m_srcClip && m_srcClip->isConnected()) {
        rod = m_srcClip->getRegionOfDefinition(args.time);
        return true;
    }
    return false;
}

void CorridorKeyPlugin::getClipPreferences(OFX::ClipPreferencesSetter& clipPreferences)
{
    // Output is always RGBA float
    clipPreferences.setClipComponents(*m_dstClip, OFX::ePixelComponentRGBA);
    clipPreferences.setClipBitDepth(*m_dstClip, OFX::eBitDepthFloat);

    // Prefer RGBA float input
    clipPreferences.setClipComponents(*m_srcClip, OFX::ePixelComponentRGBA);

    // AlphaHint prefers single-channel alpha
    if (m_alphaHintClip) {
        clipPreferences.setClipComponents(*m_alphaHintClip, OFX::ePixelComponentAlpha);
    }
    clipPreferences.setClipBitDepth(*m_srcClip, OFX::eBitDepthFloat);
}

void CorridorKeyPlugin::changedParam(
    const OFX::InstanceChangedArgs& /*args*/, const std::string& paramName)
{
    if (paramName == kParamMode) {
        // Could enable/disable BiRefNet model param based on mode
    }
}

bool CorridorKeyPlugin::ensureConnected()
{
    std::lock_guard<std::mutex> lock(m_ipcMutex);

    if (m_connected && m_ipc->isConnected()) {
        return true;
    }

    m_connected = m_ipc->connect();

    if (!m_connected && !m_backendLaunched) {
        // Auto-launch the backend process (non-blocking)
        launchBackend();
        // Return false for now — next render call will retry the connection
        setPersistentMessage(OFX::Message::eMessageMessage, "",
            "Starting CorridorKey backend...");
        return false;
    }

    if (!m_connected) {
        setPersistentMessage(OFX::Message::eMessageError, "",
            "Cannot connect to CorridorKey backend. "
            "Failed to auto-launch the backend server.");
    } else {
        clearPersistentMessage();
    }
    return m_connected;
}

bool CorridorKeyPlugin::launchBackend()
{
    // Build paths: %APPDATA%\CorridorKeyForResolve\venv\Scripts\python.exe
    //              %APPDATA%\CorridorKeyForResolve\server.py
    const char* appdata = std::getenv("APPDATA");
    if (!appdata) return false;

    std::string pythonPath = std::string(appdata) + "\\CorridorKeyForResolve\\venv\\Scripts\\python.exe";
    std::string scriptPath = std::string(appdata) + "\\CorridorKeyForResolve\\server.py";

    // Check that both files exist
    DWORD pyAttr = GetFileAttributesA(pythonPath.c_str());
    DWORD scriptAttr = GetFileAttributesA(scriptPath.c_str());
    if (pyAttr == INVALID_FILE_ATTRIBUTES || scriptAttr == INVALID_FILE_ATTRIBUTES) {
        return false;
    }

    // Build command line: "python.exe" "server.py"
    std::string cmdLine = "\"" + pythonPath + "\" \"" + scriptPath + "\"";

    STARTUPINFOA si = {};
    si.cb = sizeof(si);
    PROCESS_INFORMATION pi = {};

    BOOL ok = CreateProcessA(
        nullptr,
        &cmdLine[0],       // command line (mutable)
        nullptr, nullptr,  // security attributes
        FALSE,             // inherit handles
        DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP,
        nullptr,           // environment
        nullptr,           // working directory
        &si, &pi
    );

    if (ok) {
        // Don't hold handles to the child process
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
        m_backendLaunched = true;
        return true;
    }

    return false;
}

ProcessFrameParams CorridorKeyPlugin::buildParams(double time)
{
    ProcessFrameParams params;

    int modeVal = 0;
    m_mode->getValueAtTime(time, modeVal);
    params.mode = modeVal;

    int birefnetVal = 0;
    m_birefnetModel->getValueAtTime(time, birefnetVal);
    switch (birefnetVal) {
        case 0: params.birefnet_model = "general"; break;
        case 1: params.birefnet_model = "portrait"; break;
        case 2: params.birefnet_model = "matting"; break;
        default: params.birefnet_model = "general"; break;
    }

    int csVal = 0;
    m_inputColorspace->getValueAtTime(time, csVal);
    params.input_colorspace = csVal;

    m_despillStrength->getValueAtTime(time, params.despill_strength);

    bool despeckle = true;
    m_autoDespeckle->getValueAtTime(time, despeckle);
    params.auto_despeckle = despeckle;

    m_despeckleSize->getValueAtTime(time, params.despeckle_size);
    m_refinerStrength->getValueAtTime(time, params.refiner_strength);

    int outputVal = 0;
    m_outputMode->getValueAtTime(time, outputVal);
    params.output_mode = outputVal;

    return params;
}

} // namespace corridorkey
