import SwiftUI

@main
struct BiliAnalyzerApp: App {
    init() {
        BackendManager.shared.startIfNeeded()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1200, height: 700)

        Settings {
            SettingsView()
        }
    }
}
