import Foundation

/// 管理 Python 后端进程的生命周期
final class BackendManager {
    static let shared = BackendManager()

    private var process: Process?
    private let port = 8765
    private let projectDir = "/Users/liangliwei/bili-analyzer"

    private init() {}

    /// 启动后端（如果尚未运行）
    func startIfNeeded() {
        // 先检查是否已经在运行
        checkHealth { alive in
            if alive {
                print("[BackendManager] 后端已在运行")
            } else {
                self.launch()
            }
        }
    }

    /// 停止后端
    func stop() {
        guard let proc = process, proc.isRunning else { return }
        proc.terminate()
        process = nil
        print("[BackendManager] 后端已停止")
    }

    private func launch() {
        let scriptPath = "\(projectDir)/start-backend.sh"
        guard FileManager.default.fileExists(atPath: scriptPath) else {
            print("[BackendManager] start-backend.sh 不存在: \(scriptPath)")
            return
        }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/bash")
        proc.arguments = [scriptPath]
        proc.currentDirectoryURL = URL(fileURLWithPath: projectDir)

        // 后端输出写入日志文件
        let logPath = "/tmp/bili-backend.log"
        FileManager.default.createFile(atPath: logPath, contents: nil)
        let logHandle = FileHandle(forWritingAtPath: logPath)
        proc.standardOutput = logHandle
        proc.standardError = logHandle

        proc.terminationHandler = { p in
            print("[BackendManager] 后端进程退出，code=\(p.terminationStatus)")
        }

        do {
            try proc.run()
            process = proc
            print("[BackendManager] 后端已启动，PID=\(proc.processIdentifier)")
        } catch {
            print("[BackendManager] 启动失败: \(error)")
        }
    }

    private func checkHealth(completion: @escaping (Bool) -> Void) {
        guard let url = URL(string: "http://127.0.0.1:\(port)/api/notes") else {
            completion(false)
            return
        }
        var req = URLRequest(url: url)
        req.timeoutInterval = 2
        URLSession.shared.dataTask(with: req) { _, response, error in
            let alive = error == nil && (response as? HTTPURLResponse)?.statusCode == 200
            completion(alive)
        }.resume()
    }
}
