import Foundation

@MainActor
final class NoteDetailViewModel: ObservableObject {
    @Published var noteJSON: String?
    @Published var isLoading = false
    @Published var errorMessage: String?

    func load(bvid: String) async {
        isLoading = true
        errorMessage = nil
        noteJSON = nil
        do {
            let json = try await APIService.shared.fetchNoteJSON(bvid: bvid)
            noteJSON = json
        } catch {
            errorMessage = "加载失败：\(error.localizedDescription)"
        }
        isLoading = false
    }
}
