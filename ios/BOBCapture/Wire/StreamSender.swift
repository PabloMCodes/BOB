import Foundation

/// WebSocket client to the vision server: one binary message per wire message, flow control by
/// `SendGate` (never queue), automatic reconnect with backoff. Transport only — no decisions.
final class StreamSender: NSObject, URLSessionWebSocketDelegate {
    enum State: String {
        case off, connecting, connected
    }

    struct Stats {
        var state = State.off
        var sentFrames = 0
        var droppedFrames = 0
        var reconnects = 0
    }

    private let queue = DispatchQueue(label: "bob.stream", qos: .userInitiated)
    private var urlSession: URLSession!

    // Touched only on `queue`.
    private var url: URL?
    private var task: URLSessionWebSocketTask?
    private var generation = 0  // callbacks from an older connection are ignored
    private var gate = SendGate()
    private var backoff: TimeInterval = 0.5
    private var stats = Stats()

    override init() {
        super.init()
        let delegateQueue = OperationQueue()
        delegateQueue.underlyingQueue = queue
        urlSession = URLSession(configuration: .ephemeral, delegate: self, delegateQueue: delegateQueue)
    }

    /// Start streaming to `url` (e.g. ws://192.168.1.20:8765), or stop with nil.
    func configure(url: URL?) {
        queue.async {
            self.url = url
            self.disconnect()
            self.stats = Stats()  // counters describe the current streaming run only
            if url != nil {
                self.backoff = 0.5
                self.connect()
            }
        }
    }

    func snapshot() -> Stats {
        queue.sync { stats }
    }

    /// Never blocks and never queues: the message is sent now or dropped.
    func send(_ message: Data, isFrame: Bool) {
        queue.async {
            guard self.url != nil else { return }  // streaming off: not a drop
            let decision = self.gate.offer(isFrame: isFrame, connected: self.stats.state == .connected,
                                           now: ProcessInfo.processInfo.systemUptime)
            switch decision {
            case .drop:
                if isFrame { self.stats.droppedFrames += 1 }
            case .reconnect:
                if isFrame { self.stats.droppedFrames += 1 }
                self.connectionLost(generation: self.generation)
            case .send:
                guard let task = self.task else { return }
                let generation = self.generation
                task.send(.data(message)) { error in
                    self.queue.async {
                        guard generation == self.generation else { return }
                        self.gate.completed(isFrame: isFrame)
                        if error != nil {
                            self.connectionLost(generation: generation)
                        } else if isFrame {
                            self.stats.sentFrames += 1
                        }
                    }
                }
            }
        }
    }

    // MARK: - Private (on `queue`)

    private func connect() {
        guard let url else { return }
        generation += 1
        let task = urlSession.webSocketTask(with: url)
        self.task = task
        stats.state = .connecting
        task.resume()
        receive(task, generation: generation)
    }

    private func disconnect() {
        generation += 1
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        gate.reset()
    }

    /// The server never sends data; this only notices the connection closing.
    private func receive(_ task: URLSessionWebSocketTask, generation: Int) {
        task.receive { result in
            self.queue.async {
                guard generation == self.generation else { return }
                switch result {
                case .success: self.receive(task, generation: generation)
                case .failure: self.connectionLost(generation: generation)
                }
            }
        }
    }

    private func connectionLost(generation: Int) {
        guard generation == self.generation, url != nil else { return }
        disconnect()
        stats.state = .connecting
        stats.reconnects += 1
        let delay = backoff
        backoff = min(backoff * 2, 2.0)
        let retry = self.generation
        queue.asyncAfter(deadline: .now() + delay) {
            guard retry == self.generation else { return }  // reconfigured meanwhile
            self.connect()
        }
    }

    // MARK: - URLSessionWebSocketDelegate (delegate queue runs on `queue`)

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didOpenWithProtocol protocol: String?) {
        guard webSocketTask === task else { return }
        stats.state = .connected
        backoff = 0.5
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        guard webSocketTask === task else { return }
        connectionLost(generation: generation)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        guard task === self.task else { return }
        connectionLost(generation: generation)
    }
}
