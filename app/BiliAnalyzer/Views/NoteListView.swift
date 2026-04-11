import SwiftUI

struct NoteListView: View {
    @ObservedObject var vm: NoteListViewModel
    @Binding var selection: NoteItem?

    var body: some View {
        List(vm.filteredNotes, selection: $selection) { note in
            NoteCardView(note: note)
                .tag(note)
                .contextMenu {
                    Button(role: .destructive) {
                        Task { await vm.delete(bvid: note.bvid) }
                    } label: {
                        Label("删除", systemImage: "trash")
                    }
                }
        }
        .listStyle(.sidebar)
        .searchable(text: $vm.searchText, prompt: "搜索笔记")
        .overlay {
            if vm.isLoading {
                ProgressView("加载中...")
            } else if vm.filteredNotes.isEmpty && !vm.searchText.isEmpty {
                ContentUnavailableView.search(text: vm.searchText)
            } else if vm.notes.isEmpty {
                ContentUnavailableView(
                    "暂无笔记",
                    systemImage: "note.text",
                    description: Text("在 Chrome 扩展中分析视频后，笔记会出现在这里")
                )
            }
        }
        .toolbar {
            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await vm.load() }
                } label: {
                    Image(systemName: "arrow.clockwise")
                }
                .help("刷新笔记列表")
            }
        }
        .task { await vm.load() }
        .refreshable { await vm.load() }
    }
}
