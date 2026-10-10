import Foundation

/// Swift mirror of `vision/schema` C1 (iPhone -> vision), schema v2.
/// Field names, enums and optionality must match Python exactly. BOBCaptureTests decode the shared
/// fixtures in tests/fixtures/ to catch drift. Python is the validator; this side only encodes.
enum WireSchema {
    static let version = 2
}

enum TrackingStateWire: String, Codable {
    case normal
    case limited
    case notAvailable = "not_available"
}

enum TrackingReasonWire: String, Codable {
    case initializing
    case excessiveMotion = "excessive_motion"
    case insufficientFeatures = "insufficient_features"
    case relocalizing
}

/// Mirrors UIDeviceOrientation. Python decides the rotation (Swift stays thin).
enum DeviceOrientationWire: String, Codable {
    case unknown
    case portrait
    case portraitUpsideDown = "portrait_upside_down"
    case landscapeLeft = "landscape_left"
    case landscapeRight = "landscape_right"
    case faceUp = "face_up"
    case faceDown = "face_down"
}

/// ARCamera.intrinsics relative to ARCamera.imageResolution (ref_width x ref_height).
struct IntrinsicsWire: Codable, Equatable {
    var fx: Double
    var fy: Double
    var cx: Double
    var cy: Double
    var refWidth: Int
    var refHeight: Int
}

/// Describes the JPEG payload after the header. Pixels are in sensor orientation.
struct ImageInfoWire: Codable, Equatable {
    var width: Int
    var height: Int
    var encoding = "jpeg"
    var deviceOrientation: DeviceOrientationWire
    var byteLength: Int
}

/// One ARFrame with a JPEG payload (~10 Hz).
struct FramePacket: Codable, Equatable {
    var schemaVersion = WireSchema.version
    var msgType = "frame"
    var sessionId: UUID
    var seqId: UInt64
    var iphoneFrameTsNs: UInt64
    var trackingState: TrackingStateWire
    var trackingReason: TrackingReasonWire?   // only when tracking_state == limited
    var cameraTransform: [Double]             // 16 floats, column-major (simd_float4x4)
    var image: ImageInfoWire
    var intrinsics: IntrinsicsWire?
}

/// Pose-only ARFrame (~20 Hz) so pose history survives dropped frames.
struct PosePacket: Codable, Equatable {
    var schemaVersion = WireSchema.version
    var msgType = "pose"
    var sessionId: UUID
    var seqId: UInt64
    var iphoneFrameTsNs: UInt64
    var trackingState: TrackingStateWire
    var trackingReason: TrackingReasonWire?
    var cameraTransform: [Double]
}
