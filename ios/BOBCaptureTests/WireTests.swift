import CoreImage
import simd
import XCTest

/// The Swift side of the wire contract, checked against the fixtures Python also uses.
final class SchemaFixtureTests: XCTestCase {
    private func fixture(_ name: String) throws -> Data {
        let bundle = Bundle(for: SchemaFixtureTests.self)
        let root = try XCTUnwrap(bundle.url(forResource: "fixtures", withExtension: nil),
                                 "tests/fixtures not bundled — check project.yml")
        return try Data(contentsOf: root.appendingPathComponent("valid/\(name).json"))
    }

    /// JSON as a comparable object; nulls dropped (Swift omits nil optionals, Python defaults them).
    private func normalized(_ data: Data) throws -> NSDictionary {
        func strip(_ value: Any) -> Any {
            if let dict = value as? [String: Any] {
                return dict.filter { !($0.value is NSNull) }.mapValues(strip)
            }
            if let array = value as? [Any] { return array.map(strip) }
            return value
        }
        return strip(try JSONSerialization.jsonObject(with: data)) as! NSDictionary
    }

    private func assertRoundTrip<T: Codable>(_ type: T.Type, _ name: String) throws {
        let data = try fixture(name)
        let packet = try WireCodec.makeDecoder().decode(T.self, from: data)
        let reencoded = try WireCodec.makeEncoder().encode(packet)
        XCTAssertEqual(try normalized(reencoded), try normalized(data), "\(name) changed shape in Swift")
    }

    func testFrameFixturesRoundTrip() throws {
        try assertRoundTrip(FramePacket.self, "frame_normal")
        try assertRoundTrip(FramePacket.self, "frame_limited_rotated")
    }

    func testPoseFixtureRoundTrips() throws {
        try assertRoundTrip(PosePacket.self, "pose_normal")
    }

    func testSchemaVersionMatchesPython() throws {
        let packet = try WireCodec.makeDecoder().decode(FramePacket.self, from: try fixture("frame_normal"))
        XCTAssertEqual(packet.schemaVersion, WireSchema.version)
    }
}

final class WireCodecTests: XCTestCase {
    private func samplePose() -> PosePacket {
        PosePacket(sessionId: UUID(), seqId: 7, iphoneFrameTsNs: 183_456_789_012_345,
                   trackingState: .normal, trackingReason: nil,
                   cameraTransform: WireCodec.columnMajor(matrix_identity_float4x4))
    }

    func testMessageFraming() throws {
        let payload = Data([0xFF, 0xD8, 0x01])
        let message = try WireCodec.message(samplePose(), payload: payload)
        let headerLen = Int(message.prefix(4).reduce(0) { $0 << 8 | UInt32($1) })
        let header = message.subdata(in: 4..<(4 + headerLen))
        XCTAssertEqual(message.count, 4 + headerLen + payload.count)
        XCTAssertEqual(message.suffix(payload.count), payload)
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: header) as? [String: Any])
        XCTAssertEqual(json["msg_type"] as? String, "pose")
        XCTAssertEqual(json["seq_id"] as? Int, 7)
        XCTAssertNil(json["tracking_reason"], "nil optionals must be omitted, not encoded")
    }

    func testTimestampIsIntegerJSON() throws {
        let message = try WireCodec.message(samplePose())
        let text = String(decoding: message.dropFirst(4), as: UTF8.self)
        XCTAssertTrue(text.contains("\"iphone_frame_ts_ns\":183456789012345"), text)
    }

    func testRecordFraming() {
        let record = WireCodec.record(Data([1, 2, 3]))
        XCTAssertEqual(Array(record), [0, 0, 0, 3, 1, 2, 3])
    }

    func testColumnMajorPutsTranslationLast() {
        var m = matrix_identity_float4x4
        m.columns.3 = SIMD4<Float>(0.5, 0, -1.2, 1)
        let v = WireCodec.columnMajor(m)
        XCTAssertEqual(v.count, 16)
        XCTAssertEqual(v[12], 0.5, accuracy: 1e-6)
        XCTAssertEqual(v[14], -1.2, accuracy: 1e-6)
        XCTAssertEqual(Array(v[3...3] + v[7...7] + v[11...11]), [0, 0, 0], "w of rotation columns")
        XCTAssertEqual(v[15], 1)
    }

    func testColumnMajorRotationColumns() {
        // 90 degrees about +Y: column 2 (camera +Z axis) = (1, 0, 0).
        let m = simd_float4x4(simd_quatf(angle: .pi / 2, axis: SIMD3<Float>(0, 1, 0)))
        let v = WireCodec.columnMajor(m)
        XCTAssertEqual(v[8], 1, accuracy: 1e-6)
        XCTAssertEqual(v[10], 0, accuracy: 1e-6)
    }

    func testTimestampRounding() {
        XCTAssertEqual(WireCodec.timestampNs(183_456.789_012_345), 183_456_789_012_345)
    }

    /// Regenerates tests/fixtures/recordings/swift_golden.bobrec, which Python's tests decode — the
    /// real Swift -> Python check. Runs only when asked:
    ///   TEST_RUNNER_BOB_GOLDEN_PATH=<repo>/tests/fixtures/recordings/swift_golden.bobrec xcodebuild test ...
    func testExportGoldenRecording() throws {
        guard let path = ProcessInfo.processInfo.environment["BOB_GOLDEN_PATH"] else {
            throw XCTSkip("set TEST_RUNNER_BOB_GOLDEN_PATH to regenerate the golden recording")
        }
        let context = CIContext()
        let image = CIImage(color: CIColor(red: 0.2, green: 0.6, blue: 0.9)).cropped(to: CGRect(x: 0, y: 0, width: 64, height: 48))
        let jpeg = try XCTUnwrap(context.jpegRepresentation(of: image, colorSpace: CGColorSpace(name: CGColorSpace.sRGB)!))

        let session = UUID(uuidString: "6F9619FF-8B86-4D11-B42D-00C04FC964FF")!
        var yawed = matrix_identity_float4x4 * simd_float4x4(simd_quatf(angle: .pi / 2, axis: SIMD3<Float>(0, 1, 0)))
        yawed.columns.3 = SIMD4<Float>(1.0, 0.1, -2.0, 1)
        let frame = FramePacket(
            sessionId: session, seqId: 0, iphoneFrameTsNs: 183_456_789_012_345,
            trackingState: .normal, trackingReason: nil, cameraTransform: WireCodec.columnMajor(yawed),
            image: ImageInfoWire(width: 64, height: 48, deviceOrientation: .portrait, byteLength: jpeg.count),
            intrinsics: IntrinsicsWire(fx: 1450.2, fy: 1450.2, cx: 959.5, cy: 719.5, refWidth: 1920, refHeight: 1440)
        )
        let pose = PosePacket(
            sessionId: session, seqId: 1, iphoneFrameTsNs: 183_456_839_012_345,
            trackingState: .limited, trackingReason: .excessiveMotion, cameraTransform: WireCodec.columnMajor(yawed)
        )
        var file = Data()
        file.append(WireCodec.record(try WireCodec.message(frame, payload: jpeg)))
        file.append(WireCodec.record(try WireCodec.message(pose)))
        try file.write(to: URL(fileURLWithPath: path))
    }

    func testRecorderWritesFramedMessages() throws {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        let recorder = Recorder(directory: dir)
        try recorder.start()
        recorder.write(Data([9, 9]))
        recorder.write(Data([8]))
        let url = try XCTUnwrap(recorder.stop())
        XCTAssertEqual(Array(try Data(contentsOf: url)), [0, 0, 0, 2, 9, 9, 0, 0, 0, 1, 8])
        XCTAssertEqual(recorder.messageCount, 2)
    }
}
