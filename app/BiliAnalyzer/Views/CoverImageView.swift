import SwiftUI

/// 用 URLSession 加载远程图片，比 AsyncImage 更可靠
struct CoverImageView: View {
    let urlString: String
    @State private var image: NSImage?

    var body: some View {
        Group {
            if let image {
                Image(nsImage: image)
                    .resizable()
                    .aspectRatio(16/9, contentMode: .fill)
            } else {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color.gray.opacity(0.15))
                    .overlay(
                        Image(systemName: "play.rectangle")
                            .foregroundColor(.gray.opacity(0.4))
                    )
            }
        }
        .frame(width: 120, height: 68)
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .task(id: urlString) {
            await loadImage()
        }
    }

    private func loadImage() async {
        let https = urlString.replacingOccurrences(of: "http://", with: "https://")
        guard let url = URL(string: https) else { return }
        do {
            let (data, _) = try await URLSession.shared.data(from: url)
            if let nsImage = NSImage(data: data) {
                image = nsImage
            }
        } catch {
            // 静默失败，显示 fallback
        }
    }
}
