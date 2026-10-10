import XCTest

/// Latest-frame-wins flow control of the WebSocket sender (AGENTS rule 6): never queue.
final class SendGateTests: XCTestCase {
    func testDisconnectedDropsEverything() {
        var gate = SendGate()
        XCTAssertEqual(gate.offer(isFrame: true, connected: false, now: 0), .drop)
        XCTAssertEqual(gate.offer(isFrame: false, connected: false, now: 0), .drop)
        XCTAssertFalse(gate.frameInFlight)
    }

    func testOneFrameInFlightNewerFrameDropped() {
        var gate = SendGate()
        XCTAssertEqual(gate.offer(isFrame: true, connected: true, now: 0), .send)
        XCTAssertEqual(gate.offer(isFrame: true, connected: true, now: 0.1), .drop)
        gate.completed(isFrame: true)
        XCTAssertEqual(gate.offer(isFrame: true, connected: true, now: 0.2), .send)
    }

    func testPosesFlowWhileFrameInFlightButAreCapped() {
        var gate = SendGate(maxPosesInFlight: 2)
        XCTAssertEqual(gate.offer(isFrame: true, connected: true, now: 0), .send)
        XCTAssertEqual(gate.offer(isFrame: false, connected: true, now: 0), .send)
        XCTAssertEqual(gate.offer(isFrame: false, connected: true, now: 0), .send)
        XCTAssertEqual(gate.offer(isFrame: false, connected: true, now: 0), .drop)
        gate.completed(isFrame: false)
        XCTAssertEqual(gate.offer(isFrame: false, connected: true, now: 0), .send)
    }

    func testStalledFrameRequestsReconnect() {
        var gate = SendGate(stallTimeout: 2.0)
        XCTAssertEqual(gate.offer(isFrame: true, connected: true, now: 10), .send)
        XCTAssertEqual(gate.offer(isFrame: true, connected: true, now: 11.9), .drop)
        XCTAssertEqual(gate.offer(isFrame: true, connected: true, now: 12.1), .reconnect)
    }

    func testResetClearsInFlight() {
        var gate = SendGate()
        _ = gate.offer(isFrame: true, connected: true, now: 0)
        _ = gate.offer(isFrame: false, connected: true, now: 0)
        gate.reset()
        XCTAssertFalse(gate.frameInFlight)
        XCTAssertEqual(gate.posesInFlight, 0)
        gate.completed(isFrame: false)  // late completion from the dead connection
        XCTAssertEqual(gate.posesInFlight, 0)
    }
}
