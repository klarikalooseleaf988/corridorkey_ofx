#pragma once

#include <string>
#include <vector>
#include <cstdint>
#include <optional>
#include <functional>

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>

namespace corridorkey {

// Must match Python ipc_protocol.py
enum class MessageType : uint32_t {
    // Plugin -> Backend
    PING = 0,
    PROCESS_FRAME = 1,
    SHUTDOWN = 2,
    LOAD_MODEL = 3,

    // Backend -> Plugin
    PONG = 100,
    FRAME_DONE = 101,
    ERROR_RESP = 102,
    MODEL_LOADED = 103,
    STATUS = 104,
};

enum class OutputMode : int {
    PROCESSED = 0,
    MATTE = 1,
    FOREGROUND = 2,
    COMPOSITE = 3,
};

enum class AlphaHintMode : int {
    AUTO = 0,
    EXTERNAL = 1,
};

enum class InputColorspace : int {
    SRGB = 0,
    LINEAR = 1,
};

struct FrameHeader {
    uint32_t width;
    uint32_t height;
    uint32_t channels;
    uint32_t reserved;
};

struct ProcessFrameParams {
    int width = 0;
    int height = 0;
    int mode = 0;
    std::string birefnet_model = "general";
    int input_colorspace = 0;
    double despill_strength = 1.0;
    bool auto_despeckle = true;
    int despeckle_size = 400;
    double refiner_strength = 1.0;
    int output_mode = 0;
    bool has_alpha_hint = false;
};

struct FrameResult {
    int width = 0;
    int height = 0;
    int channels = 4;
    int output_mode = 0;
    double processing_time_ms = 0.0;
    bool success = false;
    std::string error_message;
};

// Shared memory region wrapper
class SharedMemoryRegion {
public:
    SharedMemoryRegion(const std::string& name, size_t size);
    ~SharedMemoryRegion();

    bool open();
    void close();
    bool isOpen() const { return m_ptr != nullptr; }

    void writeFrame(int width, int height, int channels, const float* data);
    bool readFrame(int& width, int& height, int& channels, std::vector<float>& data);

    void* ptr() const { return m_ptr; }

private:
    std::string m_name;
    size_t m_size;
    HANDLE m_handle = nullptr;
    void* m_ptr = nullptr;
};

// Named pipe client for control messages
class IPCClient {
public:
    static constexpr const char* PIPE_NAME = "\\\\.\\pipe\\CorridorKeyForResolve";
    static constexpr const char* SHM_INPUT = "CorridorKeyForResolve_Input";
    static constexpr const char* SHM_OUTPUT = "CorridorKeyForResolve_Output";
    static constexpr const char* SHM_ALPHA_HINT = "CorridorKeyForResolve_AlphaHint";

    static constexpr int MAX_FRAME_WIDTH = 4096;
    static constexpr int MAX_FRAME_HEIGHT = 4096;
    static constexpr int BYTES_PER_PIXEL = 16;  // 4 channels * float32
    static constexpr size_t MAX_SHM_SIZE = (size_t)MAX_FRAME_WIDTH * MAX_FRAME_HEIGHT * BYTES_PER_PIXEL;
    static constexpr int FRAME_HEADER_SIZE = 16;

    IPCClient();
    ~IPCClient();

    bool connect();
    void disconnect();
    bool isConnected() const { return m_pipeHandle != INVALID_HANDLE_VALUE; }

    bool ping();

    // Process a frame through the backend
    FrameResult processFrame(
        const float* inputRGBA,
        int width, int height,
        const ProcessFrameParams& params,
        const float* alphaHint = nullptr,  // optional external alpha hint
        float* outputRGBA = nullptr        // output buffer (caller-allocated)
    );

    // Request model loading
    bool loadModel(const std::string& model, const std::string& variant = "general");

    // Request shutdown
    bool shutdown();

    std::string lastError() const { return m_lastError; }

private:
    bool sendMessage(MessageType type, const std::string& jsonPayload = "{}");
    bool readMessage(MessageType& outType, std::string& outPayload);
    std::string buildProcessFrameJson(const ProcessFrameParams& params);

    HANDLE m_pipeHandle = INVALID_HANDLE_VALUE;
    SharedMemoryRegion m_shmInput;
    SharedMemoryRegion m_shmOutput;
    SharedMemoryRegion m_shmAlphaHint;
    std::string m_lastError;
};

} // namespace corridorkey
