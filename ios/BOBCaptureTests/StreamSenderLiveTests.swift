import CoreImage
import simd
import XCTest

/// Swift sender -> real Python server (`uv run python -m vision.server --no-view --record`). Runs only
/// when asked, like the golden export:
///   TEST_RUNNER_BOB_SERVER_URL=ws://127.0.0.1:8765 xcodebuild test ... -only-testing:BOBCaptureTests/StreamSenderLiveTests
/// Streams 10 Hz frames + poses for BOB_STREAM_SECONDS (default 3). With BOB_EXPECT_RECONNECT=1 the
/// server is killed and restarted meanwhile, and the sender must reconnect on its own.
final class StreamSenderLiveTests: XCTestCase {
    func testStreamsToPythonServer() throws {
        let env = ProcessInfo.processInfo.environment
        guard let urlString = env["BOB_SERVER_URL"], let url = URL(string: urlString) else {
            throw XCTSkip("set TEST_RUNNER_BOB_SERVER_URL to stream to a running vision.server")
        }
        let seconds = Double(env["BOB_STREAM_SECONDS"] ?? "3") ?? 3
        let context = CIContext()
        let image = CIImage(color: CIColor(red: 0.2, green: 0.6, blue: 0.9)).cropped(to: CGRect(x: 0, y: 0, width: 64, height: 48))
        let jpeg = try XCTUnwrap(context.jpegRepresentation(of: image, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!))

        let sender = StreamSender()
        sender.configure(url: url)
        let deadline = Date().addingTimeInterval(5)
        while sender.snapshot().state != .connected && Date() < deadline {
            Thread.sleep(forTimeInterval: 0.05)
        }
        XCTAssertEqual(sender.snapshot().state, .connected, "could not connect to \(urlString)")

        let session = UUID()
        var seq: UInt64 = 0
        let start = ProcessInfo.processInfo.systemUptime
        for i in 0..<Int(seconds * 10) {
            let ts = WireCodec.timestampNs(start + Double(i) * 0.1)
            let frame = FramePacket(
                sessionId: session, seqId: seq, iphoneFrameTsNs: ts, trackingState: .normal, trackingReason: nil,
                cameraTransform: WireCodec.columnMajor(matrix_identity_float4x4),
                image: ImageInfoWire(width: 64, height: 48, deviceOrientation: .portrait, byteLength: jpeg.count),
                intrinsics: nil
            )
            sender.send(try WireCodec.message(frame, payload: jpeg), isFrame: true)
            let pose = PosePacket(
                sessionId: session, seqId: seq + 1, iphoneFrameTsNs: ts + 50_000_000, trackingState: .normal,
                trackingReason: nil, cameraTransform: WireCodec.columnMajor(matrix_identity_float4x4)
            )
            sender.send(try WireCodec.message(pose), isFrame: false)
            seq += 2
            Thread.sleep(forTimeInterval: 0.1)
        }
        Thread.sleep(forTimeInterval: 0.3)
        let stats = sender.snapshot()
        print("[live] state \(stats.state.rawValue) sent \(stats.sentFrames) dropped \(stats.droppedFrames) reconnects \(stats.reconnects)")
        XCTAssertEqual(stats.state, .connected)
        XCTAssertGreaterThan(stats.sentFrames, 0)
        if env["BOB_EXPECT_RECONNECT"] == "1" {
            XCTAssertGreaterThanOrEqual(stats.reconnects, 1)
        }
        sender.configure(url: nil)
    }
}
