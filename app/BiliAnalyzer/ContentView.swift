import SwiftUI

struct ContentView: View {
    @StateObject private var listVM = NoteListViewModel()
    @State private var selectedNote: NoteItem?

    var body: some View {
        NavigationSplitView {
            NoteListView(vm: listVM, selection: $selectedNote)
                .navigationSplitViewColumnWidth(min: 280, ideal: 320)
        } detail: {
            if let note = selectedNote {
                NoteDetailView(note: note)
            } else {
                ContentUnavailableView(
                    "选择一个笔记",
                    systemImage: "doc.text.magnifyingglass",
                    description: Text("从左侧列表选择笔记查看详情")
                )
            }
        }
        .frame(minWidth: 800, minHeight: 500)
    }
}
