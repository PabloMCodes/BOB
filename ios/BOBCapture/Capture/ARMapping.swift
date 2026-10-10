import ARKit
import UIKit

// The only place that translates Apple types into wire types. No decisions here: values are
// copied as-is and Python interprets them.

extension TrackingStateWire {
    static func from(_ state: ARCamera.TrackingState) -> (TrackingStateWire, TrackingReasonWire?) {
        switch state {
        case .normal:
            return (.normal, nil)
        case .notAvailable:
            return (.notAvailable, nil)
        case .limited(let reason):
            switch reason {
            case .initializing: return (.limited, .initializing)
            case .excessiveMotion: return (.limited, .excessiveMotion)
            case .insufficientFeatures: return (.limited, .insufficientFeatures)
            case .relocalizing: return (.limited, .relocalizing)
            // A reason added by a future iOS: report "not available" (consumers stop) rather than guess.
            @unknown default: return (.notAvailable, nil)
            }
        }
    }
}

extension DeviceOrientationWire {
    init(_ orientation: UIDeviceOrientation) {
        switch orientation {
        case .portrait: self = .portrait
        case .portraitUpsideDown: self = .portraitUpsideDown
        case .landscapeLeft: self = .landscapeLeft
        case .landscapeRight: self = .landscapeRight
        case .faceUp: self = .faceUp
        case .faceDown: self = .faceDown
        default: self = .unknown
        }
    }
}

extension IntrinsicsWire {
    /// simd_float3x3 columns: (fx, 0, 0), (0, fy, 0), (cx, cy, 1).
    init(_ camera: ARCamera) {
        let k = camera.intrinsics
        self.init(
            fx: Double(k.columns.0.x), fy: Double(k.columns.1.y),
            cx: Double(k.columns.2.x), cy: Double(k.columns.2.y),
            refWidth: Int(camera.imageResolution.width), refHeight: Int(camera.imageResolution.height)
        )
    }
}
