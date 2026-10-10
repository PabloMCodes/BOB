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
    var stream = StreamSender.State.off
    var streamSentHz = 0.0
    var streamDropped = 0
    var streamReconnects = 0
    var error: String?
}

/// ARSession -> throttled frame/pose wire messages -> recorder and WebSocket sender.
/// Copies Apple values into wire types and nothing more (AGENTS.md rule 1).
final class CaptureController: NSObject, ObservableObject, ARSessionDelegate {
    @Published private(set) var stats = CaptureStats()
    @Published var settings = CaptureSettings() { didSet { settingsBox.set(settings) } }
    @Published private(set) var isRecording = false
    @Published private(set) var lastRecording: URL?
    @Published private(set) var isStreaming = false
    @Published var serverURL = UserDefaults.standard.string(forKey: "serverURL") ?? "ws://192.168.1.10:8765" {
        didSet {
            UserDefaults.standard.set(serverURL, forKey: "serverURL")
            if isStreaming { sender.configure(url: URL(string: serverURL)) }
        }
    }
    let lidarAvailable = ARWorldTrackingConfiguration.supportsSceneReconstruction(.mesh)

    private var session: ARSession?
    private let queue = DispatchQueue(label: "bob.capture", qos: .userInitiated)
    private let settingsBox = Locked(CaptureSettings())
    private let orientationBox = Locked(DeviceOrientationWire.unknown)
    private let recordingBox = Locked(false)
    private let encoder = FrameEncoder()
    private let encodeQueue = DispatchQueue(label: "bob.encode", qos: .userInitiated)
    private let encoderBusy = Locked(false)
    private let recorder = Recorder()
    private let sender = StreamSender()

    // Touched only on `queue`.
    private var sessionId = UUID()
    private var seq: UInt64 = 0
    private var lastFrameTs: TimeInterval = -.infinity
    private var lastPoseTs: TimeInterval = -.infinity
    private var window = StatsWindow()
    private var lastSentFrames = 0

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

    func toggleStreaming() {
        isStreaming.toggle()
        sender.configure(url: isStreaming ? URL(string: serverURL) : nil)
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

        // Copy plain values out of the ARFrame and return fast: ARKit stops delivering images if the
        // delegate retains too many ARFrames. Only the pixel buffer travels to the encoder.
        let (state, reason) = TrackingStateWire.from(frame.camera.trackingState)
        let transform = WireCodec.columnMajor(frame.camera.transform)
        let tsNs = WireCodec.timestampNs(ts)
        lastPoseTs = ts

        // Latest frame wins (AGENTS rule 6): one encode in flight; if busy, send this pose without the image.
        if wantFrame && !encoderBusy.get() {
            lastFrameTs = ts
            encoderBusy.set(true)
            let job = EncodeJob(
                pixelBuffer: frame.capturedImage, sessionId: sessionId, tsNs: tsNs, state: state,
                reason: reason, transform: transform, intrinsics: IntrinsicsWire(frame.camera),
                orientation: orientationBox.get(), settings: settings
            )
            encodeQueue.async { self.encode(job) }
            return
        }
        emitPose(sessionId: sessionId, tsNs: tsNs, state: state, reason: reason, transform: transform)
    }

    private func emitPose(sessionId: UUID, tsNs: UInt64, state: TrackingStateWire,
                          reason: TrackingReasonWire?, transform: [Double]) {
        let packet = PosePacket(
            sessionId: sessionId, seqId: nextSeq(), iphoneFrameTsNs: tsNs,
            trackingState: state, trackingReason: reason, cameraTransform: transform
        )
        window.poses += 1
        do {
            emit(try WireCodec.message(packet), isFrame: false, state: state, reason: reason)
        } catch {
            publishError("encode failed: \(error)")
        }
    }

    /// On `encodeQueue`. The result hops back to `queue`, so seq_id stays in file order.
    private func encode(_ job: EncodeJob) {
        let started = CACurrentMediaTime()
        let jpeg = encoder.jpeg(job.pixelBuffer, longSide: job.settings.longSide, quality: job.settings.jpegQuality)
        let encodeMs = (CACurrentMediaTime() - started) * 1000
        queue.async {
            defer { self.encoderBusy.set(false) }
            guard job.sessionId == self.sessionId else { return }  // session reset mid-encode: stale
            guard let jpeg else {
                self.publishError("JPEG encoding failed")
                return
            }
            let packet = FramePacket(
                sessionId: job.sessionId, seqId: self.nextSeq(), iphoneFrameTsNs: job.tsNs,
                trackingState: job.state, trackingReason: job.reason, cameraTransform: job.transform,
                image: ImageInfoWire(width: jpeg.width, height: jpeg.height,
                                     deviceOrientation: job.orientation, byteLength: jpeg.data.count),
                intrinsics: job.intrinsics
            )
            self.window.addFrame(bytes: jpeg.data.count, encodeMs: encodeMs, size: "\(jpeg.width)x\(jpeg.height)")
            do {
                self.emit(try WireCodec.message(packet, payload: jpeg.data), isFrame: true,
                          state: job.state, reason: job.reason)
            } catch {
                self.publishError("encode failed: \(error)")
            }
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

    private func emit(_ message: Data, isFrame: Bool, state: TrackingStateWire, reason: TrackingReasonWire?) {
        if recordingBox.get() {
            recorder.write(message)
        }
        sender.send(message, isFrame: isFrame)  // sent now or dropped, never queued
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
        let stream = sender.snapshot()
        snapshot.stream = stream.state
        snapshot.streamSentHz = Double(max(0, stream.sentFrames - lastSentFrames)) / elapsed
        snapshot.streamDropped = stream.droppedFrames
        snapshot.streamReconnects = stream.reconnects
        lastSentFrames = stream.sentFrames
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

/// Everything the encoder needs, copied out of an ARFrame so the frame itself is released immediately.
private struct EncodeJob {
    let pixelBuffer: CVPixelBuffer
    let sessionId: UUID
    let tsNs: UInt64
    let state: TrackingStateWire
    let reason: TrackingReasonWire?
    let transform: [Double]
    let intrinsics: IntrinsicsWire
    let orientation: DeviceOrientationWire
    let settings: CaptureSettings
}
