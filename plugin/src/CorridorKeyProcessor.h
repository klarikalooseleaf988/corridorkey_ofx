#pragma once

#include "ofxsImageEffect.h"
#include "IPCClient.h"

namespace corridorkey {

class CorridorKeyProcessor {
public:
    CorridorKeyProcessor(OFX::ImageEffect& effect);

    void setImages(OFX::Image* src, OFX::Image* dst, OFX::Image* alphaHint = nullptr);
    void setRenderWindow(const OfxRectI& window);
    void setParams(const ProcessFrameParams& params);
    void setIPCClient(IPCClient* ipc);

    void process();

    // Utility: copy source image to destination
    static void copyImage(OFX::Image* src, OFX::Image* dst, const OfxRectI& window);

private:
    void extractSourcePixels(std::vector<float>& buffer);
    void extractAlphaHintPixels(std::vector<float>& buffer);
    void writeOutputPixels(const float* data, int channels);

    OFX::ImageEffect& m_effect;
    OFX::Image* m_srcImg = nullptr;
    OFX::Image* m_dstImg = nullptr;
    OFX::Image* m_alphaHintImg = nullptr;
    OfxRectI m_renderWindow = {0, 0, 0, 0};
    ProcessFrameParams m_params;
    IPCClient* m_ipc = nullptr;
};

} // namespace corridorkey
