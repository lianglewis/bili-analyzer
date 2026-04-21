import SwiftUI

struct SettingsView: View {
    @State private var apiKey = ""
    @State private var apiURL = ""
    @State private var model = ""
    @State private var status: Status = .idle
    @State private var loaded = false

    private let base = "http://127.0.0.1:8765"

    enum Status: Equatable {
        case idle, saving, saved, error(String)
    }

    var body: some View {
        Form {
            Section("Claude API") {
                SecureField("API Key", text: $apiKey)
                    .textFieldStyle(.roundedBorder)
                TextField("API URL", text: $apiURL)
                    .textFieldStyle(.roundedBorder)
                TextField("Model", text: $model)
                    .textFieldStyle(.roundedBorder)
            }

            Section {
                HStack {
                    Button("保存") { save() }
                        .disabled(status == .saving)
                    statusLabel
                }
            }
        }
        .formStyle(.grouped)
        .frame(width: 480)
        .padding()
        .task { await load() }
    }

    @ViewBuilder
    private var statusLabel: some View {
        switch status {
        case .idle: EmptyView()
        case .saving: ProgressView().controlSize(.small)
        case .saved: Text("已保存").foregroundStyle(.green)
        case .error(let msg): Text(msg).foregroundStyle(.red)
        }
    }

    // MARK: - Network

    private func load() async {
        guard let url = URL(string: "\(base)/api/config") else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            let cfg = try JSONDecoder().decode(ConfigDTO.self, from: data)
            apiURL = cfg.claude_api_url
            model = cfg.claude_model
            // 脱敏 key 仅展示占位，不覆盖空输入框
            loaded = true
        } catch {
            status = .error("后端未运行")
        }
    }

    private func save() {
        status = .saving
        Task {
            guard let url = URL(string: "\(base)/api/config") else { return }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")

            var body: [String: String] = [
                "claude_model": model,
                "claude_api_url": apiURL,
            ]
            if !apiKey.isEmpty { body["claude_api_key"] = apiKey }

            req.httpBody = try? JSONEncoder().encode(body)
            do {
                let (_, resp) = try await URLSession.shared.data(for: req)
                if let http = resp as? HTTPURLResponse, http.statusCode == 200 {
                    status = .saved
                } else {
                    status = .error("保存失败")
                }
            } catch {
                status = .error("后端未运行")
            }
        }
    }
}

private struct ConfigDTO: Decodable {
    let claude_api_key: String
    let claude_model: String
    let claude_api_url: String
}
