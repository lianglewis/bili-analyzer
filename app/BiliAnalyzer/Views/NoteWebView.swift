import SwiftUI
import WebKit

/// WKWebView 渲染交互式笔记（加载 note-viewer.html + 注入 JSON）
struct NoteWebView: NSViewRepresentable {
    let noteJSON: String

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.userContentController.add(context.coordinator, name: "jumpToTime")
        config.userContentController.add(context.coordinator, name: "playTTS")
        config.userContentController.add(context.coordinator, name: "termAsk")

        // 允许 WKWebView 访问本地文件
        config.preferences.setValue(true, forKey: "allowFileAccessFromFileURLs")

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.navigationDelegate = context.coordinator
        context.coordinator.pendingJSON = noteJSON

        if let htmlURL = Bundle.main.url(forResource: "note-viewer", withExtension: "html") {
            let dir = htmlURL.deletingLastPathComponent()
            webView.loadFileURL(htmlURL, allowingReadAccessTo: dir)
        } else {
            // 找不到资源文件时显示错误
            webView.loadHTMLString("<h2 style='color:red;padding:20px'>note-viewer.html not found in bundle</h2>", baseURL: nil)
        }

        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        if context.coordinator.pendingJSON != noteJSON {
            context.coordinator.pendingJSON = noteJSON
            injectNote(webView: webView, json: noteJSON)
        }
    }

    private static let decodeScript = "function _b64utf8(b){var s=atob(b),a=new Uint8Array(s.length);for(var i=0;i<s.length;i++)a[i]=s.charCodeAt(i);return new TextDecoder().decode(a)}"

    private func injectNote(webView: WKWebView, json: String) {
        if let data = json.data(using: .utf8) {
            let b64 = data.base64EncodedString()
            let js = "\(Self.decodeScript);window.renderNote(JSON.parse(_b64utf8('\(b64)')))"
            webView.evaluateJavaScript(js)
        }
    }

    class Coordinator: NSObject, WKNavigationDelegate, WKScriptMessageHandler {
        var pendingJSON: String?
        private static let apiBase = "http://127.0.0.1:8765"

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            guard let json = pendingJSON else { return }
            if let data = json.data(using: .utf8) {
                let b64 = data.base64EncodedString()
                let js = "\(NoteWebView.decodeScript);window.renderNote(JSON.parse(_b64utf8('\(b64)')))"
                webView.evaluateJavaScript(js) { _, error in
                    if let error = error {
                        print("[NoteWebView] JS error: \(error)")
                    }
                }
            }
        }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            if message.name == "jumpToTime", let seconds = message.body as? Int {
                NotificationCenter.default.post(
                    name: .jumpToTime,
                    object: nil,
                    userInfo: ["seconds": seconds]
                )
            } else if message.name == "playTTS", let text = message.body as? String {
                handleTTS(text: text, webView: message.webView)
            } else if message.name == "termAsk", let payload = message.body as? String {
                handleTermAsk(payload: payload, webView: message.webView)
            }
        }

        private func handleTTS(text: String, webView: WKWebView?) {
            guard let url = URL(string: "\(Self.apiBase)/api/tts") else { return }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try? JSONSerialization.data(withJSONObject: ["text": text])

            URLSession.shared.dataTask(with: req) { data, response, error in
                DispatchQueue.main.async {
                    guard let data = data, error == nil,
                          let httpResp = response as? HTTPURLResponse,
                          httpResp.statusCode == 200 else {
                        webView?.evaluateJavaScript("window._onTtsResult(null)")
                        return
                    }
                    let b64 = data.base64EncodedString()
                    webView?.evaluateJavaScript("window._onTtsResult('\(b64)')")
                }
            }.resume()
        }

        private func handleTermAsk(payload: String, webView: WKWebView?) {
            guard let url = URL(string: "\(Self.apiBase)/api/ask") else { return }
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = payload.data(using: .utf8)
            req.timeoutInterval = 60

            URLSession.shared.dataTask(with: req) { data, response, error in
                DispatchQueue.main.async {
                    guard let data = data, error == nil,
                          let json = String(data: data, encoding: .utf8) else {
                        let fallback = #"{"answer":null}"#
                        webView?.evaluateJavaScript("window._onAskResult('\(fallback)')")
                        return
                    }
                    let escaped = json
                        .replacingOccurrences(of: "\\", with: "\\\\")
                        .replacingOccurrences(of: "'", with: "\\'")
                        .replacingOccurrences(of: "\n", with: "\\n")
                        .replacingOccurrences(of: "\r", with: "")
                    webView?.evaluateJavaScript("window._onAskResult('\(escaped)')")
                }
            }.resume()
        }
    }
}

extension Notification.Name {
    static let jumpToTime = Notification.Name("jumpToTime")
}
