import Foundation

/// Appends wire messages to Documents/recordings/bob_<time>.bobrec (see WireCodec.record).
/// Visible in the Files app ("On My iPhone > BOB Capture") and shareable via AirDrop.
/// Read on the Mac with `uv run python -m tools.inspect_recording <file>`.
final class Recorder {
    static var defaultDirectory: URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("recordings", isDirectory: true)
    }

    private let directory: URL
    private let queue = DispatchQueue(label: "bob.recorder")
    private var handle: FileHandle?
    private var url: URL?
    private let count = Locked(0)

    var messageCount: Int { count.get() }

    init(directory: URL = Recorder.defaultDirectory) {
        self.directory = directory
    }

    @discardableResult
    func start(now: Date = Date()) throws -> URL {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.dateFormat = "yyyyMMdd_HHmmss"
        let url = directory.appendingPathComponent("bob_\(formatter.string(from: now)).bobrec")
        FileManager.default.createFile(atPath: url.path, contents: nil)
        let handle = try FileHandle(forWritingTo: url)
        queue.sync {
            self.handle = handle
            self.url = url
        }
        count.set(0)
        return url
    }

    /// Non-blocking: file I/O happens on the recorder's own queue, never the capture queue.
    func write(_ message: Data) {
        queue.async {
            guard let handle = self.handle else { return }
            try? handle.write(contentsOf: WireCodec.record(message))
            self.count.mutate { $0 += 1 }
        }
    }

    /// Flushes pending writes and closes the file. Returns the recording URL.
    @discardableResult
    func stop() -> URL? {
        queue.sync {
            try? handle?.close()
            handle = nil
            return url
        }
    }
}
