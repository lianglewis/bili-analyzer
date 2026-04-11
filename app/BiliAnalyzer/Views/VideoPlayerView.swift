import SwiftUI
import WebKit

/// WKWebView 加载 B站视频页面，支持时间戳跳转
struct VideoPlayerView: NSViewRepresentable {
    let videoURL: String

    func makeCoordinator() -> Coordinator {
        Coordinator()
    }

    func makeNSView(context: Context) -> WKWebView {
        let webView = WKWebView()
        context.coordinator.webView = webView

        if let url = URL(string: videoURL) {
            webView.load(URLRequest(url: url))
        }

        // 监听时间戳跳转
        context.coordinator.observer = NotificationCenter.default.addObserver(
            forName: .jumpToTime,
            object: nil,
            queue: .main
        ) { notification in
            guard let seconds = notification.userInfo?["seconds"] as? Int else { return }
            // B站播放器的跳转方式：修改 URL hash 或用 JS
            let js = """
            (function() {
                var video = document.querySelector('video');
                if (video) { video.currentTime = \(seconds); video.play(); }
            })()
            """
            webView.evaluateJavaScript(js)
        }

        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        // URL 变化时重新加载
        if let url = URL(string: videoURL),
           webView.url?.absoluteString.contains(url.host ?? "") != true {
            webView.load(URLRequest(url: url))
        }
    }

    class Coordinator {
        weak var webView: WKWebView?
        var observer: Any?

        deinit {
            if let observer = observer {
                NotificationCenter.default.removeObserver(observer)
            }
        }
    }
}
