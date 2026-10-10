import ARKit
import Foundation
import UIKit

struct CaptureSettings: Equatable {
    var longSide = 1920      // JPEG long side; 1920 = native ARKit frame (needed for 3 m+ head/foot crops)
    var frameHz = 10.0       // frame messages (pose + JPEG)
    var poseHz = 20.0        // pose-only messages in between
    var jpegQuality = 0.7
}

struct CaptureStats {
    var tracking = "starting"
    var trackingState = TrackingStateWire.notAvailable
    var orientation = DeviceOrientationWire.unknown
    var session = "-"
    var seq: UInt64 = 0
    var frameHz = 0.0
    var poseHz = 0.0
    var jpegKB = 0.0
    var megabytesPerSecond = 0.0
    var encodeMs = 0.0
    var imageSize = "-"
    var recordedMessages = 0
    var error: String?
}

/// ARSession -> throttled frame/pose wire messages -> recorder (Step 5: also the WebSocket sender).
/// Copies Apple values into wire types and nothing more (AGENTS.md rule 1).
final class CaptureController: NSObject, ObservableObject, ARSessionDelegate {
    @Published private(set) var stats = CaptureStats()
    @Published var settings = CaptureSettings() { didSet { settingsBox.set(settings) } }
    @Published private(set) var isRecording = false
    @Published private(set) var lastRecording: URL?
    let lidarAvailable = ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh)

    private var session: ARSession?
    private let queue = DispatchQueue(label: "bob.capture", qos: .userInitiated)
    private let settingsBox = Locked(CaptureSettings())
    private let orientationBox = Locked(DeviceOrientationWire.unknown)
    private let recordingBox = Locked(false)
    private let encoder = FrameEncoder()
    private let recorder = Recorder()

    // Touched only on `queue`.
    private var sessionId = UUID()
    private var seq: UInt64 = 0
    private var lastFrameTs: TimeInterval = -.infinity
    private var lastPoseTs: TimeInterval = -.infinity
    private var window = StatsWindow()

    func start(session: ARSession) {
        self.session = session
        session.delegate = self
        session.delegateQueue = queue
        UIDevice.current.beginGeneratingDeviceOrientationNotifications()
        NotificationCenter.default.addObserver(
            self, selector: #selector(orientationChanged),
            name: UIDevice.orientationDidChangeNotification, object: nil
        )
        orientationChanged()
        UIApplication.shared.isIdleTimerDisabled = true  // screen lock would suspend the AR session
        resetSession()
    }

    /// Restart tracking with a new world origin => new session_id, seq from 0. Consumers must discard
    /// everything from the previous session (AGENTS.md rule 5).
    func resetSession() {
        guard ARWorldTrackingConfiguration.isSupported, let session else {
            stats.error = "ARKit world tracking is not supported on this device"
            return
        }
        let config = ARWorldTrackingConfiguration()
        config.worldAlignment = .gravity
        queue.async {
            self.sessionId = UUID()
            self.seq = 0
            self.lastFrameTs = -.infinity
            self.lastPoseTs = -.infinity
        }
        session.run(config, options: [.resetTracking, .removeExistingAnchors])
    }

    func toggleRecording() {
        if isRecording {
            recordingBox.set(false)
            lastRecording = recorder.stop()
            isRecording = false
        } else {
            do {
                try recorder.start()
                lastRecording = nil
                recordingBox.set(true)
                isRecording = true
            } catch {
                stats.error = "recording failed: \(error.localizedDescription)"
            }
        }
    }

    @objc private func orientationChanged() {
        orientationBox.set(DeviceOrientationWire(UIDevice.current.orientation))
    }

    // MARK: - ARSessionDelegate (called on `queue`)

    func session(_ session: ARSession, didUpdate frame: ARFrame) {
        let settings = settingsBox.get()
        let ts = frame.timestamp
        let wantFrame = ts - lastFrameTs >= 1.0 / settings.frameHz
        let wantPose = ts - lastPoseTs >= 1.0 / settings.poseHz
        guard wantFrame || wantPose else { return }  // cheap exit for the other ~50 fps

        let (state, reason) = TrackingStateWire.from(frame.camera.trackingState)
        let transform = WireCodec.columnMajor(frame.camera.transform)
        let tsNs = WireCodec.timestampNs(ts)
        do {
            if wantFrame {
                lastFrameTs = ts
                lastPoseTs = ts  // a frame message carries the pose too
                let started = CACurrentMediaTime()
                guard let jpeg = encoder.jpeg(frame.capturedImage, longSide: settings.longSide, quality: settings.jpegQuality) else {
                    publishError("JPEG encoding failed")
                    return
                }
                let packet = FramePacket(
                    sessionId: sessionId, seqId: nextSeq(), iphoneFrameTsNs: tsNs,
                    trackingState: state, trackingReason: reason, cameraTransform: transform,
                    image: ImageInfoWire(width: jpeg.width, height: jpeg.height,
                                         deviceOrientation: orientationBox.get(), byteLength: jpeg.data.count),
                    intrinsics: IntrinsicsWire(frame.camera)
                )
                window.addFrame(bytes: jpeg.data.count, encodeMs: (CACurrentMediaTime() - started) * 1000,
                                size: "\(jpeg.width)x\(jpeg.height)")
                emit(try WireCodec.message(packet, payload: jpeg.data), state: state, reason: reason)
            } else {
                lastPoseTs = ts
                let packet = PosePacket(
                    sessionId: sessionId, seqId: nextSeq(), iphoneFrameTsNs: tsNs,
                    trackingState: state, trackingReason: reason, cameraTransform: transform
                )
                window.poses += 1
                emit(try WireCodec.message(packet), state: state, reason: reason)
            }
        } catch {
            publishError("encode failed: \(error)")
        }
    }

    func session(_ session: ARSession, didFailWithError error: Error) {
        publishError("AR session failed: \(error.localizedDescription)")
    }

    func sessionInterruptionEnded(_ session: ARSession) {
        // Backgrounding / call / lock: the world origin can't be trusted any more.
        DispatchQueue.main.async { self.resetSession() }
    }

    // MARK: - Private (on `queue`)

    private func nextSeq() -> UInt64 {
        defer { seq += 1 }
        return seq
    }

    private func emit(_ message: Data, state: TrackingStateWire, reason: TrackingReasonWire?) {
        if recordingBox.get() {
            recorder.write(message)
        }
        // Step 5: hand `message` to the WebSocket sender here (latest-frame-wins, never queue).
        window.bytes += message.count
        let now = CACurrentMediaTime()
        guard now - window.start >= 0.5 else { return }

        let elapsed = now - window.start
        var snapshot = CaptureStats()
        snapshot.trackingState = state
        snapshot.tracking = state.rawValue + (reason.map { " (\($0.rawValue))" } ?? "")
        snapshot.orientation = orientationBox.get()
        snapshot.session = String(sessionId.uuidString.prefix(8))
        snapshot.seq = seq
        snapshot.frameHz = Double(window.frames) / elapsed
        snapshot.poseHz = Double(window.poses) / elapsed
        snapshot.jpegKB = window.frames > 0 ? Double(window.jpegBytes) / Double(window.frames) / 1024 : 0
        snapshot.megabytesPerSecond = Double(window.bytes) / elapsed / 1_000_000
        snapshot.encodeMs = window.frames > 0 ? window.encodeMs / Double(window.frames) : 0
        snapshot.imageSize = window.size
        snapshot.recordedMessages = recorder.messageCount
        window = StatsWindow(start: now, size: window.size)
        DispatchQueue.main.async { self.stats = snapshot }
    }

    private func publishError(_ message: String) {
        DispatchQueue.main.async { self.stats.error = message }
    }
}

/// Rolling counters for the debug overlay (~2 Hz refresh).
private struct StatsWindow {
    var start = CACurrentMediaTime()
    var frames = 0
    var poses = 0
    var bytes = 0
    var jpegBytes = 0
    var encodeMs = 0.0
    var size = "-"

    mutating func addFrame(bytes: Int, encodeMs: Double, size: String) {
        frames += 1
        jpegBytes += bytes
        self.encodeMs += encodeMs
        self.size = size
    }
}
