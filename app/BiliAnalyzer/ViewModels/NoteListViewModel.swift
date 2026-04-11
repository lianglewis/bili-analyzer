import Foundation

@MainActor
final class NoteListViewModel: ObservableObject {
    @Published var notes: [NoteItem] = []
    @Published var searchText: String = ""
    @Published var isLoading = false
    @Published var errorMessage: String?

    var filteredNotes: [NoteItem] {
        if searchText.isEmpty { return notes }
        let q = searchText.lowercased()
        return notes.filter {
            $0.video_title.lowercased().contains(q) ||
            $0.category.lowercased().contains(q)
        }
    }

    func load() async {
        isLoading = true
        errorMessage = nil
        do {
            notes = try await APIService.shared.fetchNotes()
        } catch {
            errorMessage = "加载失败：\(error.localizedDescription)"
        }
        isLoading = false
    }

    func delete(bvid: String) async {
        do {
            try await APIService.shared.deleteNote(bvid: bvid)
            notes.removeAll { $0.bvid == bvid }
        } catch {
            errorMessage = "删除失败：\(error.localizedDescription)"
        }
    }
}
