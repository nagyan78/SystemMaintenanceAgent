using System.Diagnostics;
using System.Net.Http;
using System.Net.Sockets;
using System.Text;
using System.Windows.Forms;

namespace StandardProductSystemLauncher;

internal static class Program
{
    private const int BackendPort = 8000;
    private const int FrontendPort = 5173;

    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Encoding.RegisterProvider(CodePagesEncodingProvider.Instance);

        var executableName = Path.GetFileNameWithoutExtension(Environment.ProcessPath) ?? string.Empty;
        var root = FindProjectRoot(AppContext.BaseDirectory);
        if (root is null)
        {
            MessageBox.Show(
                "未找到项目目录。请把启动器放在 standard_product_system 项目根目录。",
                "产品标准体系维护智能体",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        if (executableName.Contains("停止", StringComparison.OrdinalIgnoreCase))
        {
            StopServices();
            return;
        }

        StartServices(root);
    }

    private static string? FindProjectRoot(string startDirectory)
    {
        var current = new DirectoryInfo(startDirectory);
        while (current is not null)
        {
            if (Directory.Exists(Path.Combine(current.FullName, "backend")) &&
                Directory.Exists(Path.Combine(current.FullName, "frontend")) &&
                File.Exists(Path.Combine(current.FullName, ".venv", "Scripts", "python.exe")))
            {
                return current.FullName;
            }
            current = current.Parent;
        }
        return null;
    }

    private static void StartServices(string root)
    {
        var python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        var frontend = Path.Combine(root, "frontend");
        var packageJson = Path.Combine(frontend, "package.json");
        if (!File.Exists(python) || !File.Exists(packageJson))
        {
            MessageBox.Show(
                "启动条件不完整：请确认 .venv 和 frontend/package.json 存在。",
                "启动失败",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return;
        }

        var started = new List<Process>();
        try
        {
            var backendWasRunning = IsPortOpen(BackendPort);
            var frontendWasRunning = IsPortOpen(FrontendPort);

            if (!backendWasRunning)
            {
                var backend = new ProcessStartInfo
                {
                    FileName = python,
                    WorkingDirectory = root,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                backend.ArgumentList.Add("-m");
                backend.ArgumentList.Add("uvicorn");
                backend.ArgumentList.Add("backend.app.main:app");
                backend.ArgumentList.Add("--host");
                backend.ArgumentList.Add("127.0.0.1");
                backend.ArgumentList.Add("--port");
                backend.ArgumentList.Add(BackendPort.ToString());
                started.Add(Process.Start(backend) ?? throw new InvalidOperationException("无法启动后端进程。"));
            }

            if (!frontendWasRunning)
            {
                var frontendStart = new ProcessStartInfo
                {
                    FileName = Path.Combine(Environment.SystemDirectory, "cmd.exe"),
                    WorkingDirectory = frontend,
                    UseShellExecute = false,
                    CreateNoWindow = true,
                };
                frontendStart.ArgumentList.Add("/d");
                frontendStart.ArgumentList.Add("/c");
                frontendStart.ArgumentList.Add("npm.cmd");
                frontendStart.ArgumentList.Add("run");
                frontendStart.ArgumentList.Add("dev");
                frontendStart.ArgumentList.Add("--");
                frontendStart.ArgumentList.Add("--host");
                frontendStart.ArgumentList.Add("127.0.0.1");
                started.Add(Process.Start(frontendStart) ?? throw new InvalidOperationException("无法启动前端进程。"));
            }

            var backendReady = WaitForBackend(TimeSpan.FromSeconds(30));
            var frontendReady = WaitForPort(FrontendPort, TimeSpan.FromSeconds(30));
            if (!backendReady || !frontendReady)
            {
                throw new InvalidOperationException(
                    $"服务启动超时。后端：{(backendReady ? "正常" : "未就绪")}；前端：{(frontendReady ? "正常" : "未就绪")}。\n\n可使用 README 中的 PowerShell 命令查看详细日志。");
            }

            Process.Start(new ProcessStartInfo
            {
                FileName = "http://127.0.0.1:5173",
                UseShellExecute = true,
            });

            var message = backendWasRunning || frontendWasRunning
                ? "系统已经运行，已打开前端页面。"
                : "后端和前端启动成功，已打开前端页面。";
            MessageBox.Show(message, "启动成功", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
        catch (Exception exception)
        {
            foreach (var process in started)
            {
                TryKill(process);
            }
            MessageBox.Show(exception.Message, "启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private static void StopServices()
    {
        var pids = FindListeningProcessIds(BackendPort)
            .Concat(FindListeningProcessIds(FrontendPort))
            .Where(pid => pid != Environment.ProcessId)
            .Distinct()
            .ToList();

        foreach (var pid in pids)
        {
            try
            {
                using var process = Process.GetProcessById(pid);
                TryKill(process);
            }
            catch
            {
                // The process may have exited between netstat and lookup.
            }
        }

        Thread.Sleep(800);
        var backendStopped = !IsPortOpen(BackendPort);
        var frontendStopped = !IsPortOpen(FrontendPort);
        var message = backendStopped && frontendStopped
            ? "后端和前端已经停止。需要重启时双击“启动系统.exe”。"
            : $"停止操作已执行。后端：{(backendStopped ? "已停止" : "仍在运行")}；前端：{(frontendStopped ? "已停止" : "仍在运行")}。";
        MessageBox.Show(message, "停止系统", MessageBoxButtons.OK,
            backendStopped && frontendStopped ? MessageBoxIcon.Information : MessageBoxIcon.Warning);
    }

    private static bool WaitForBackend(TimeSpan timeout)
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(2) };
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            try
            {
                var response = client.GetAsync("http://127.0.0.1:8000/api/health").GetAwaiter().GetResult();
                if (response.IsSuccessStatusCode)
                {
                    return true;
                }
            }
            catch
            {
                // The server is still starting.
            }
            Thread.Sleep(500);
        }
        return false;
    }

    private static bool WaitForPort(int port, TimeSpan timeout)
    {
        var deadline = DateTime.UtcNow + timeout;
        while (DateTime.UtcNow < deadline)
        {
            if (IsPortOpen(port))
            {
                return true;
            }
            Thread.Sleep(500);
        }
        return false;
    }

    private static bool IsPortOpen(int port)
    {
        try
        {
            using var client = new TcpClient();
            return client.ConnectAsync("127.0.0.1", port).Wait(TimeSpan.FromMilliseconds(400));
        }
        catch
        {
            return false;
        }
    }

    private static IEnumerable<int> FindListeningProcessIds(int port)
    {
        var startInfo = new ProcessStartInfo
        {
            FileName = Path.Combine(Environment.SystemDirectory, "netstat.exe"),
            Arguments = "-ano -p tcp",
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
        };
        using var process = Process.Start(startInfo);
        if (process is null)
        {
            yield break;
        }

        var output = process.StandardOutput.ReadToEnd();
        process.WaitForExit(3000);
        foreach (var line in output.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var fields = line.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length < 5 || !fields[0].Equals("TCP", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            if (!fields[3].Equals("LISTENING", StringComparison.OrdinalIgnoreCase) ||
                !fields[1].EndsWith($":{port}", StringComparison.OrdinalIgnoreCase))
            {
                continue;
            }
            if (int.TryParse(fields[^1], out var pid))
            {
                yield return pid;
            }
        }
    }

    private static void TryKill(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                process.WaitForExit(3000);
            }
        }
        catch
        {
            // A process that already exited is considered stopped.
        }
    }
}
