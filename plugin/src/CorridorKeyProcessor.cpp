#include "CorridorKeyProcessor.h"

#include <cstring>
#include <algorithm>

namespace corridorkey {

CorridorKeyProcessor::CorridorKeyProcessor(OFX::ImageEffect& effect)
    : m_effect(effect)
{
}

void CorridorKeyProcessor::setImages(OFX::Image* src, OFX::Image* dst, OFX::Image* alphaHint)
{
    m_srcImg = src;
    m_dstImg = dst;
    m_alphaHintImg = alphaHint;
}

void CorridorKeyProcessor::setRenderWindow(const OfxRectI& window)
{
    m_renderWindow = window;
}

void CorridorKeyProcessor::setParams(const ProcessFrameParams& params)
{
    m_params = params;
}

void CorridorKeyProcessor::setIPCClient(IPCClient* ipc)
{
    m_ipc = ipc;
}

void CorridorKeyProcessor::process()
{
    if (!m_srcImg || !m_dstImg || !m_ipc) {
        return;
    }

    int width = m_renderWindow.x2 - m_renderWindow.x1;
    int height = m_renderWindow.y2 - m_renderWindow.y1;

    if (width <= 0 || height <= 0) return;

    // Extract source pixels to contiguous float32 RGBA buffer
    std::vector<float> srcBuffer;
    extractSourcePixels(srcBuffer);

    // Extract alpha hint if available
    std::vector<float> alphaHintBuffer;
    const float* alphaHintPtr = nullptr;
    if (m_alphaHintImg && m_params.has_alpha_hint) {
        extractAlphaHintPixels(alphaHintBuffer);
        alphaHintPtr = alphaHintBuffer.data();
    }

    // Allocate output buffer
    std::vector<float> outputBuffer(static_cast<size_t>(width) * height * 4);

    // Send frame to backend for processing
    FrameResult result = m_ipc->processFrame(
        srcBuffer.data(),
        width, height,
        m_params,
        alphaHintPtr,
        outputBuffer.data()
    );

    if (result.success) {
        // Write processed output to destination image
        writeOutputPixels(outputBuffer.data(), 4);
    } else {
        // On failure, pass through source
        copyImage(m_srcImg, m_dstImg, m_renderWindow);
    }
}

void CorridorKeyProcessor::extractSourcePixels(std::vector<float>& buffer)
{
    int width = m_renderWindow.x2 - m_renderWindow.x1;
    int height = m_renderWindow.y2 - m_renderWindow.y1;

    buffer.resize(static_cast<size_t>(width) * height * 4);

    OfxRectI srcBounds = m_srcImg->getBounds();
    int srcRowBytes = m_srcImg->getRowBytes();
    int srcNComps = m_srcImg->getPixelComponentCount();

    for (int y = m_renderWindow.y1; y < m_renderWindow.y2; ++y) {
        if (y < srcBounds.y1 || y >= srcBounds.y2) continue;

        const auto* srcRow = static_cast<const float*>(m_srcImg->getPixelAddress(m_renderWindow.x1, y));
        if (!srcRow) continue;

        int localY = y - m_renderWindow.y1;
        float* dstRow = buffer.data() + static_cast<size_t>(localY) * width * 4;

        for (int x = 0; x < width; ++x) {
            const float* srcPix = srcRow + x * srcNComps;
            float* dstPix = dstRow + x * 4;

            // Copy RGB, set A
            dstPix[0] = srcPix[0];
            dstPix[1] = (srcNComps > 1) ? srcPix[1] : srcPix[0];
            dstPix[2] = (srcNComps > 2) ? srcPix[2] : srcPix[0];
            dstPix[3] = (srcNComps > 3) ? srcPix[3] : 1.0f;
        }
    }
}

void CorridorKeyProcessor::extractAlphaHintPixels(std::vector<float>& buffer)
{
    int width = m_renderWindow.x2 - m_renderWindow.x1;
    int height = m_renderWindow.y2 - m_renderWindow.y1;

    buffer.resize(static_cast<size_t>(width) * height * 4);

    OfxRectI bounds = m_alphaHintImg->getBounds();
    int nComps = m_alphaHintImg->getPixelComponentCount();

    for (int y = m_renderWindow.y1; y < m_renderWindow.y2; ++y) {
        if (y < bounds.y1 || y >= bounds.y2) continue;

        const auto* srcRow = static_cast<const float*>(
            m_alphaHintImg->getPixelAddress(m_renderWindow.x1, y));
        if (!srcRow) continue;

        int localY = y - m_renderWindow.y1;
        float* dstRow = buffer.data() + static_cast<size_t>(localY) * width * 4;

        for (int x = 0; x < width; ++x) {
            const float* srcPix = srcRow + x * nComps;
            float val = srcPix[0];  // Use first component as alpha hint

            // If RGBA, use alpha channel instead
            if (nComps == 4) {
                val = srcPix[3];
            }

            float* dstPix = dstRow + x * 4;
            dstPix[0] = val;
            dstPix[1] = val;
            dstPix[2] = val;
            dstPix[3] = val;
        }
    }
}

void CorridorKeyProcessor::writeOutputPixels(const float* data, int channels)
{
    int width = m_renderWindow.x2 - m_renderWindow.x1;

    OfxRectI dstBounds = m_dstImg->getBounds();
    int dstNComps = m_dstImg->getPixelComponentCount();

    for (int y = m_renderWindow.y1; y < m_renderWindow.y2; ++y) {
        if (y < dstBounds.y1 || y >= dstBounds.y2) continue;

        auto* dstRow = static_cast<float*>(m_dstImg->getPixelAddress(m_renderWindow.x1, y));
        if (!dstRow) continue;

        int localY = y - m_renderWindow.y1;
        const float* srcRow = data + static_cast<size_t>(localY) * width * channels;

        for (int x = 0; x < width; ++x) {
            const float* srcPix = srcRow + x * channels;
            float* dstPix = dstRow + x * dstNComps;

            // Copy available channels
            int copyChans = std::min(channels, dstNComps);
            for (int c = 0; c < copyChans; ++c) {
                dstPix[c] = srcPix[c];
            }
            // Fill remaining destination channels
            for (int c = copyChans; c < dstNComps; ++c) {
                dstPix[c] = (c == 3) ? 1.0f : 0.0f;
            }
        }
    }
}

void CorridorKeyProcessor::copyImage(OFX::Image* src, OFX::Image* dst, const OfxRectI& window)
{
    if (!src || !dst) return;

    OfxRectI srcBounds = src->getBounds();
    OfxRectI dstBounds = dst->getBounds();
    int srcNComps = src->getPixelComponentCount();
    int dstNComps = dst->getPixelComponentCount();

    for (int y = window.y1; y < window.y2; ++y) {
        if (y < srcBounds.y1 || y >= srcBounds.y2) continue;
        if (y < dstBounds.y1 || y >= dstBounds.y2) continue;

        const auto* srcRow = static_cast<const float*>(src->getPixelAddress(window.x1, y));
        auto* dstRow = static_cast<float*>(dst->getPixelAddress(window.x1, y));
        if (!srcRow || !dstRow) continue;

        int width = window.x2 - window.x1;
        for (int x = 0; x < width; ++x) {
            const float* sp = srcRow + x * srcNComps;
            float* dp = dstRow + x * dstNComps;

            int copyChans = std::min(srcNComps, dstNComps);
            for (int c = 0; c < copyChans; ++c) {
                dp[c] = sp[c];
            }
            for (int c = copyChans; c < dstNComps; ++c) {
                dp[c] = (c == 3) ? 1.0f : 0.0f;
            }
        }
    }
}

} // namespace corridorkey
