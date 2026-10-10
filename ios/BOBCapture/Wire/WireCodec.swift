import Foundation
import simd

/// Byte layout shared with `vision/schema/wire.py` and `vision/recording.py`.
enum WireCodec {
    /// snake_case keys, nil optionals omitted (Python defaults them to null).
    static func makeEncoder() -> JSONEncoder {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        return encoder
    }

    static func makeDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    /// One wire message: [uint32 big-endian header_len][header JSON][payload].
    static func message<Header: Encodable>(_ header: Header, payload: Data = Data()) throws -> Data {
        let json = try makeEncoder().encode(header)
        var out = bigEndian(UInt32(json.count))
        out.append(json)
        out.append(payload)
        return out
    }

    /// Recording framing: [uint32 big-endian message_len][message] — one record per WebSocket message.
    static func record(_ message: Data) -> Data {
        var out = bigEndian(UInt32(message.count))
        out.append(message)
        return out
    }

    /// simd_float4x4 is column-major: columns 0...3, each (x, y, z, w); translation is column 3,
    /// so indices 12...14 hold x, y, z. Python rejects row-major input (bottom row must be 0,0,0,1).
    static func columnMajor(_ m: simd_float4x4) -> [Double] {
        [m.columns.0, m.columns.1, m.columns.2, m.columns.3].flatMap {
            [Double($0.x), Double($0.y), Double($0.z), Double($0.w)]
        }
    }

    /// ARFrame.timestamp (seconds since boot, Double) -> integer nanoseconds. Never send a Double:
    /// Python's schema requires a strict integer.
    static func timestampNs(_ seconds: TimeInterval) -> UInt64 {
        UInt64((seconds * 1_000_000_000).rounded())
    }

    private static func bigEndian(_ value: UInt32) -> Data {
        withUnsafeBytes(of: value.bigEndian) { Data($0) }
    }
}

/// Minimal lock box for values shared between the main thread and capture queues.
final class Locked<Value> {
    private var value: Value
    private let lock = NSLock()

    init(_ value: Value) { self.value = value }

    func get() -> Value {
        lock.lock()
        defer { lock.unlock() }
        return value
    }

    func set(_ newValue: Value) {
        lock.lock()
        value = newValue
        lock.unlock()
    }

    func mutate(_ body: (inout Value) -> Void) {
        lock.lock()
        body(&value)
        lock.unlock()
    }
}
