import SwiftUI

@main
struct BOBCaptureApp: App {
    @StateObject private var controller = CaptureController()

    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(controller)
        }
    }
}
