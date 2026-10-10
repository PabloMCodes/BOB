import ARKit
import RealityKit
import SwiftUI

/// Camera preview + debug overlay + record / reset / settings. Display only — no decisions.
struct ContentView: View {
    @EnvironmentObject var controller: CaptureController

    var body: some View {
        ZStack {
            ARViewContainer(controller: controller)
                .ignoresSafeArea()
            VStack(alignment: .leading, spacing: 12) {
                StatsPanel(stats: controller.stats, lidar: controller.lidarAvailable,
                           recording: controller.isRecording)
                Spacer()
                Controls()
            }
            .padding()
        }
    }
}

private struct ARViewContainer: UIViewRepresentable {
    let controller: CaptureController

    func makeUIView(context: Context) -> ARView {
        let view = ARView(frame: .zero, cameraMode: .ar, automaticallyConfigureSession: false)
        controller.start(session: view.session)
        return view
    }

    func updateUIView(_ uiView: ARView, context: Context) {}
}

private struct StatsPanel: View {
    let stats: CaptureStats
    let lidar: Bool
    let recording: Bool

    private var trackingColor: Color {
        switch stats.trackingState {
        case .normal: return .green
        case .limited: return .orange
        case .notAvailable: return .red
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("tracking  \(stats.tracking)").foregroundColor(trackingColor)
            Text("session   \(stats.session)   seq \(stats.seq)")
            Text(String(format: "frames    %.1f Hz  %@  %.0f KB  enc %.1f ms", stats.frameHz, stats.imageSize, stats.jpegKB, stats.encodeMs))
            Text(String(format: "poses     %.1f Hz   stream %.2f MB/s", stats.poseHz, stats.megabytesPerSecond))
            Text("orient    \(stats.orientation.rawValue)   LiDAR \(lidar ? "yes" : "no")")
            if recording {
                Text("● REC     \(stats.recordedMessages) messages").foregroundColor(.red)
            }
            if let error = stats.error {
                Text("error     \(error)").foregroundColor(.red)
            }
        }
        .font(.system(size: 12, design: .monospaced))
        .foregroundColor(.white)
        .padding(8)
        .background(Color.black.opacity(0.6))
        .cornerRadius(8)
    }
}

private struct Controls: View {
    @EnvironmentObject var controller: CaptureController

    var body: some View {
        HStack(spacing: 12) {
            Button(controller.isRecording ? "Stop" : "Record") { controller.toggleRecording() }
                .buttonStyle(.borderedProminent)
                .tint(controller.isRecording ? .red : .blue)
            Button("Reset session") { controller.resetSession() }
                .buttonStyle(.bordered)
            Menu("Settings") {
                Picker("Resolution", selection: $controller.settings.longSide) {
                    Text("1920 (full)").tag(1920)
                    Text("1280").tag(1280)
                    Text("640").tag(640)
                }
                Picker("Frame rate", selection: $controller.settings.frameHz) {
                    Text("5 Hz").tag(5.0)
                    Text("10 Hz").tag(10.0)
                    Text("15 Hz").tag(15.0)
                }
            }
            .buttonStyle(.bordered)
            if let url = controller.lastRecording {
                ShareLink(item: url) { Label("Share", systemImage: "square.and.arrow.up") }
                    .buttonStyle(.bordered)
            }
        }
        .tint(.white)
    }
}
