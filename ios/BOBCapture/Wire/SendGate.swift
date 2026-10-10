import Foundation

/// Latest-frame-wins flow control for the WebSocket sender (AGENTS rule 6), kept pure so it is
/// unit-tested on the Simulator. Never queues: at most one frame in flight — a frame offered while
/// the previous one is still being sent is dropped (the server sees the seq_id gap). Poses are tiny
/// and may have a few in flight. A frame stuck longer than `stallTimeout` means the link is dead.
struct SendGate {
    enum Decision: Equatable {
        case send
        case drop
        case reconnect  // in-flight frame stalled: tear the connection down
    }

    var maxPosesInFlight = 4
    var stallTimeout: TimeInterval = 2.0

    private(set) var frameInFlight = false
    private(set) var frameStartedAt: TimeInterval = 0
    private(set) var posesInFlight = 0

    mutating func offer(isFrame: Bool, connected: Bool, now: TimeInterval) -> Decision {
        guard connected else { return .drop }
        if isFrame {
            if frameInFlight {
                return now - frameStartedAt > stallTimeout ? .reconnect : .drop
            }
            frameInFlight = true
            frameStartedAt = now
            return .send
        }
        guard posesInFlight < maxPosesInFlight else { return .drop }
        posesInFlight += 1
        return .send
    }

    mutating func completed(isFrame: Bool) {
        if isFrame {
            frameInFlight = false
        } else {
            posesInFlight = max(0, posesInFlight - 1)
        }
    }

    mutating func reset() {
        frameInFlight = false
        posesInFlight = 0
    }
}
