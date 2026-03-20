#pragma once

#include "ofxsImageEffect.h"
#include "ofxsMultiThread.h"
#include "IPCClient.h"

#include <memory>
#include <mutex>

namespace corridorkey {

// Parameter names
constexpr const char* kParamMode = "mode";
constexpr const char* kParamBiRefNetModel = "birefnetModel";
constexpr const char* kParamInputColorspace = "inputColorspace";
constexpr const char* kParamDespillStrength = "despillStrength";
constexpr const char* kParamAutoDespeckle = "autoDespeckle";
constexpr const char* kParamDespeckleSize = "despeckleSize";
constexpr const char* kParamRefinerStrength = "refinerStrength";
constexpr const char* kParamOutputMode = "outputMode";

// Clip names
constexpr const char* kClipSource = "Source";
constexpr const char* kClipAlphaHint = "AlphaHint";
constexpr const char* kClipOutput = "Output";

// Mode choices
constexpr const char* kModeAuto = "Auto";
constexpr const char* kModeExternal = "External";

// BiRefNet model choices
constexpr const char* kBiRefNetGeneral = "General";
constexpr const char* kBiRefNetPortrait = "Portrait";
constexpr const char* kBiRefNetMatting = "Matting";

// Colorspace choices
constexpr const char* kColorspaceSRGB = "sRGB Gamma";
constexpr const char* kColorspaceLinear = "Linear";

// Output mode choices
constexpr const char* kOutputProcessed = "Processed";
constexpr const char* kOutputMatte = "Matte";
constexpr const char* kOutputForeground = "Foreground";
constexpr const char* kOutputComposite = "Composite";


class CorridorKeyPlugin : public OFX::ImageEffect {
public:
    CorridorKeyPlugin(OfxImageEffectHandle handle);
    virtual ~CorridorKeyPlugin();

    // OFX overrides
    void render(const OFX::RenderArguments& args) override;
    bool getRegionOfDefinition(const OFX::RegionOfDefinitionArguments& args,
                               OfxRectD& rod) override;
    void getClipPreferences(OFX::ClipPreferencesSetter& clipPreferences) override;
    void changedParam(const OFX::InstanceChangedArgs& args,
                      const std::string& paramName) override;

private:
    bool ensureConnected();
    ProcessFrameParams buildParams(double time);

    // Clips
    OFX::Clip* m_srcClip;
    OFX::Clip* m_alphaHintClip;
    OFX::Clip* m_dstClip;

    // Parameters
    OFX::ChoiceParam* m_mode;
    OFX::ChoiceParam* m_birefnetModel;
    OFX::ChoiceParam* m_inputColorspace;
    OFX::DoubleParam* m_despillStrength;
    OFX::BooleanParam* m_autoDespeckle;
    OFX::IntParam* m_despeckleSize;
    OFX::DoubleParam* m_refinerStrength;
    OFX::ChoiceParam* m_outputMode;

    // IPC
    std::unique_ptr<IPCClient> m_ipc;
    std::mutex m_ipcMutex;
    bool m_connected = false;
};


class CorridorKeyPluginFactory : public OFX::PluginFactoryHelper<CorridorKeyPluginFactory> {
public:
    CorridorKeyPluginFactory()
        : OFX::PluginFactoryHelper<CorridorKeyPluginFactory>(
            "com.corridordigital.corridorkey",  // plugin identifier
            1, 0)                                // version major, minor
    {}

    void describe(OFX::ImageEffectDescriptor& desc) override;
    void describeInContext(OFX::ImageEffectDescriptor& desc,
                          OFX::ContextEnum context) override;
    OFX::ImageEffect* createInstance(OfxImageEffectHandle handle,
                                     OFX::ContextEnum context) override;
};

} // namespace corridorkey
