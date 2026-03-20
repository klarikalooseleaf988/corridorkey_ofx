#include "IPCClient.h"

#include <cstring>
#include <sstream>

namespace corridorkey {

// --- SharedMemoryRegion ---

SharedMemoryRegion::SharedMemoryRegion(const std::string& name, size_t size)
    : m_name(name)
    , m_size(size + sizeof(FrameHeader))
{
}

SharedMemoryRegion::~SharedMemoryRegion()
{
    close();
}

bool SharedMemoryRegion::open()
{
    // Convert name to wide string
    int wlen = MultiByteToWideChar(CP_UTF8, 0, m_name.c_str(), -1, nullptr, 0);
    std::wstring wname(wlen, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, m_name.c_str(), -1, &wname[0], wlen);

    m_handle = OpenFileMappingW(FILE_MAP_ALL_ACCESS, FALSE, wname.c_str());
    if (!m_handle) {
        // Try creating it (server might not have created it yet)
        DWORD sizeHigh = (DWORD)((m_size >> 32) & 0xFFFFFFFF);
        DWORD sizeLow = (DWORD)(m_size & 0xFFFFFFFF);
        m_handle = CreateFileMappingW(
            INVALID_HANDLE_VALUE, nullptr, PAGE_READWRITE,
            sizeHigh, sizeLow, wname.c_str()
        );
        if (!m_handle) {
            return false;
        }
    }

    m_ptr = MapViewOfFile(m_handle, FILE_MAP_ALL_ACCESS, 0, 0, m_size);
    if (!m_ptr) {
        CloseHandle(m_handle);
        m_handle = nullptr;
        return false;
    }

    return true;
}

void SharedMemoryRegion::close()
{
    if (m_ptr) {
        UnmapViewOfFile(m_ptr);
        m_ptr = nullptr;
    }
    if (m_handle) {
        CloseHandle(m_handle);
        m_handle = nullptr;
    }
}

void SharedMemoryRegion::writeFrame(int width, int height, int channels, const float* data)
{
    if (!m_ptr) return;

    // Write header
    FrameHeader header;
    header.width = (uint32_t)width;
    header.height = (uint32_t)height;
    header.channels = (uint32_t)channels;
    header.reserved = 0;

    auto* dst = static_cast<char*>(m_ptr);
    std::memcpy(dst, &header, sizeof(FrameHeader));

    // Write pixel data
    size_t pixelBytes = (size_t)width * height * channels * sizeof(float);
    std::memcpy(dst + sizeof(FrameHeader), data, pixelBytes);
}

bool SharedMemoryRegion::readFrame(int& width, int& height, int& channels, std::vector<float>& data)
{
    if (!m_ptr) return false;

    auto* src = static_cast<const char*>(m_ptr);
    FrameHeader header;
    std::memcpy(&header, src, sizeof(FrameHeader));

    width = (int)header.width;
    height = (int)header.height;
    channels = (int)header.channels;

    size_t pixelCount = (size_t)width * height * channels;
    data.resize(pixelCount);
    std::memcpy(data.data(), src + sizeof(FrameHeader), pixelCount * sizeof(float));

    return true;
}

// --- IPCClient ---

IPCClient::IPCClient()
    : m_shmInput(SHM_INPUT, MAX_SHM_SIZE)
    , m_shmOutput(SHM_OUTPUT, MAX_SHM_SIZE)
    , m_shmAlphaHint(SHM_ALPHA_HINT, MAX_SHM_SIZE)
{
}

IPCClient::~IPCClient()
{
    disconnect();
}

bool IPCClient::connect()
{
    // Connect to named pipe
    m_pipeHandle = CreateFileA(
        PIPE_NAME,
        GENERIC_READ | GENERIC_WRITE,
        0,
        nullptr,
        OPEN_EXISTING,
        0,
        nullptr
    );

    if (m_pipeHandle == INVALID_HANDLE_VALUE) {
        DWORD err = GetLastError();
        if (err == ERROR_PIPE_BUSY) {
            // Wait for pipe to become available
            if (WaitNamedPipeA(PIPE_NAME, 5000)) {
                m_pipeHandle = CreateFileA(
                    PIPE_NAME,
                    GENERIC_READ | GENERIC_WRITE,
                    0, nullptr, OPEN_EXISTING, 0, nullptr
                );
            }
        }
        if (m_pipeHandle == INVALID_HANDLE_VALUE) {
            m_lastError = "Failed to connect to backend pipe (error " + std::to_string(GetLastError()) + ")";
            return false;
        }
    }

    // Set pipe to byte mode
    DWORD mode = PIPE_READMODE_BYTE;
    SetNamedPipeHandleState(m_pipeHandle, &mode, nullptr, nullptr);

    // Open shared memory regions
    if (!m_shmInput.open()) {
        m_lastError = "Failed to open input shared memory";
        disconnect();
        return false;
    }
    if (!m_shmOutput.open()) {
        m_lastError = "Failed to open output shared memory";
        disconnect();
        return false;
    }
    if (!m_shmAlphaHint.open()) {
        m_lastError = "Failed to open alpha hint shared memory";
        disconnect();
        return false;
    }

    return true;
}

void IPCClient::disconnect()
{
    m_shmInput.close();
    m_shmOutput.close();
    m_shmAlphaHint.close();

    if (m_pipeHandle != INVALID_HANDLE_VALUE) {
        CloseHandle(m_pipeHandle);
        m_pipeHandle = INVALID_HANDLE_VALUE;
    }
}

bool IPCClient::ping()
{
    if (!sendMessage(MessageType::PING)) return false;

    MessageType respType;
    std::string respPayload;
    if (!readMessage(respType, respPayload)) return false;

    return respType == MessageType::PONG;
}

FrameResult IPCClient::processFrame(
    const float* inputRGBA,
    int width, int height,
    const ProcessFrameParams& params,
    const float* alphaHint,
    float* outputRGBA)
{
    FrameResult result;

    if (!isConnected()) {
        result.error_message = "Not connected to backend";
        return result;
    }

    // Write input frame to shared memory
    m_shmInput.writeFrame(width, height, 4, inputRGBA);

    // Write alpha hint if provided
    if (alphaHint && params.has_alpha_hint) {
        m_shmAlphaHint.writeFrame(width, height, 4, alphaHint);
    }

    // Send process request
    std::string json = buildProcessFrameJson(params);
    if (!sendMessage(MessageType::PROCESS_FRAME, json)) {
        result.error_message = "Failed to send process request";
        return result;
    }

    // Wait for response
    MessageType respType;
    std::string respPayload;
    if (!readMessage(respType, respPayload)) {
        result.error_message = "Failed to read response";
        return result;
    }

    if (respType == MessageType::ERROR_RESP) {
        result.error_message = "Backend error: " + respPayload;
        return result;
    }

    if (respType != MessageType::FRAME_DONE) {
        result.error_message = "Unexpected response type";
        return result;
    }

    // Read output frame from shared memory
    std::vector<float> outputData;
    int outW, outH, outC;
    if (!m_shmOutput.readFrame(outW, outH, outC, outputData)) {
        result.error_message = "Failed to read output from shared memory";
        return result;
    }

    result.width = outW;
    result.height = outH;
    result.channels = outC;
    result.success = true;

    // Copy to caller's buffer if provided
    if (outputRGBA && !outputData.empty()) {
        std::memcpy(outputRGBA, outputData.data(), outputData.size() * sizeof(float));
    }

    return result;
}

bool IPCClient::loadModel(const std::string& model, const std::string& variant)
{
    std::string json = "{\"model\":\"" + model + "\",\"variant\":\"" + variant + "\"}";
    if (!sendMessage(MessageType::LOAD_MODEL, json)) return false;

    MessageType respType;
    std::string respPayload;
    if (!readMessage(respType, respPayload)) return false;

    return respType == MessageType::MODEL_LOADED;
}

bool IPCClient::shutdown()
{
    return sendMessage(MessageType::SHUTDOWN);
}

bool IPCClient::sendMessage(MessageType type, const std::string& jsonPayload)
{
    if (m_pipeHandle == INVALID_HANDLE_VALUE) return false;

    uint32_t typeVal = static_cast<uint32_t>(type);
    uint32_t payloadLen = static_cast<uint32_t>(jsonPayload.size());

    // Build message: type(4) + length(4) + payload
    std::vector<char> msg(8 + payloadLen);
    std::memcpy(msg.data(), &typeVal, 4);
    std::memcpy(msg.data() + 4, &payloadLen, 4);
    if (payloadLen > 0) {
        std::memcpy(msg.data() + 8, jsonPayload.data(), payloadLen);
    }

    DWORD bytesWritten;
    BOOL ok = WriteFile(m_pipeHandle, msg.data(), (DWORD)msg.size(), &bytesWritten, nullptr);
    if (!ok || bytesWritten != msg.size()) {
        m_lastError = "WriteFile failed: " + std::to_string(GetLastError());
        return false;
    }
    FlushFileBuffers(m_pipeHandle);
    return true;
}

bool IPCClient::readMessage(MessageType& outType, std::string& outPayload)
{
    if (m_pipeHandle == INVALID_HANDLE_VALUE) return false;

    // Read header
    char header[8];
    DWORD bytesRead;
    BOOL ok = ReadFile(m_pipeHandle, header, 8, &bytesRead, nullptr);
    if (!ok || bytesRead != 8) {
        m_lastError = "ReadFile header failed: " + std::to_string(GetLastError());
        return false;
    }

    uint32_t typeVal, payloadLen;
    std::memcpy(&typeVal, header, 4);
    std::memcpy(&payloadLen, header + 4, 4);
    outType = static_cast<MessageType>(typeVal);

    if (payloadLen > 0) {
        outPayload.resize(payloadLen);
        ok = ReadFile(m_pipeHandle, &outPayload[0], payloadLen, &bytesRead, nullptr);
        if (!ok || bytesRead != payloadLen) {
            m_lastError = "ReadFile payload failed: " + std::to_string(GetLastError());
            return false;
        }
    } else {
        outPayload.clear();
    }

    return true;
}

std::string IPCClient::buildProcessFrameJson(const ProcessFrameParams& params)
{
    // Simple JSON builder (no external dependency)
    std::ostringstream ss;
    ss << "{"
       << "\"width\":" << params.width
       << ",\"height\":" << params.height
       << ",\"mode\":" << params.mode
       << ",\"birefnet_model\":\"" << params.birefnet_model << "\""
       << ",\"input_colorspace\":" << params.input_colorspace
       << ",\"despill_strength\":" << params.despill_strength
       << ",\"auto_despeckle\":" << (params.auto_despeckle ? "true" : "false")
       << ",\"despeckle_size\":" << params.despeckle_size
       << ",\"refiner_strength\":" << params.refiner_strength
       << ",\"output_mode\":" << params.output_mode
       << ",\"has_alpha_hint\":" << (params.has_alpha_hint ? "true" : "false")
       << "}";
    return ss.str();
}

} // namespace corridorkey
