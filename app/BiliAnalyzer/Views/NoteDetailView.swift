import SwiftUI

struct NoteDetailView: View {
    let note: NoteItem
    @StateObject private var vm = NoteDetailViewModel()
    @State private var showVideo = true

    var body: some View {
        content
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    Button {
                        showVideo.toggle()
                    } label: {
                        Image(systemName: showVideo ? "rectangle.righthalf.inset.filled" : "rectangle.split.2x1")
                    }
                    .help(showVideo ? "隐藏视频" : "显示视频")
                }

                ToolbarItem(placement: .automatic) {
                    Button {
                        Task { await vm.load(bvid: note.bvid) }
                    } label: {
                        Image(systemName: "arrow.clockwise")
                    }
                    .help("刷新")
                }
            }
            .onAppear {
                Task { await vm.load(bvid: note.bvid) }
            }
            .onChange(of: note.bvid) { _, newBvid in
                Task { await vm.load(bvid: newBvid) }
            }
    }

    @ViewBuilder
    private var content: some View {
        if vm.isLoading {
            ProgressView("加载笔记...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if let json = vm.noteJSON {
            HStack(spacing: 0) {
                NoteWebView(noteJSON: json)
                    .frame(width: 420)

                if showVideo {
                    Divider()
                    VideoPlayerView(videoURL: note.video_url)
                        .frame(maxWidth: .infinity)
                }
            }
        } else if let err = vm.errorMessage {
            VStack(spacing: 12) {
                Image(systemName: "exclamationmark.triangle")
                    .font(.largeTitle)
                    .foregroundColor(.orange)
                Text(err)
                    .foregroundColor(.secondary)
                Button("重试") {
                    Task { await vm.load(bvid: note.bvid) }
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ProgressView("准备中...")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }
}
