using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Threading;

public enum RestartResult { Relaunched, Exited, AttachFailed, StillRunning, ShellNotReading, InputFailed }

public static class SessionConsole
{
    [StructLayout(LayoutKind.Explicit)]
    struct KeyEventRecord
    {
        [FieldOffset(0)] public ushort EventType;
        [FieldOffset(4)] public int KeyDown;
        [FieldOffset(8)] public ushort RepeatCount;
        [FieldOffset(10)] public ushort VirtualKeyCode;
        [FieldOffset(12)] public ushort VirtualScanCode;
        [FieldOffset(14)] public char UnicodeChar;
        [FieldOffset(16)] public uint ControlKeyState;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct Coord { public short X, Y; }

    [StructLayout(LayoutKind.Sequential)]
    struct ScreenBufferInfo
    {
        public Coord Size, Cursor;
        public ushort Attributes;
        public short WindowLeft, WindowTop, WindowRight, WindowBottom;
        public Coord MaximumWindowSize;
    }

    [DllImport("kernel32.dll", EntryPoint = "SetConsoleCtrlHandler")] static extern bool SetConsoleCtrlIgnore(IntPtr nullHandler, bool ignore);
    [DllImport("kernel32.dll")] static extern bool GenerateConsoleCtrlEvent(uint ctrlEvent, uint processGroupId);
    [DllImport("kernel32.dll")] static extern bool AttachConsole(uint processId);
    [DllImport("kernel32.dll")] static extern bool FreeConsole();
    [DllImport("kernel32.dll")] static extern IntPtr OpenProcess(uint access, bool inherit, uint processId);
    [DllImport("kernel32.dll")] static extern uint WaitForSingleObject(IntPtr handle, uint milliseconds);
    [DllImport("kernel32.dll")] static extern bool CloseHandle(IntPtr handle);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CreateFileW(string name, uint access, uint share, IntPtr security, uint disposition, uint flags, IntPtr template);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern bool WriteConsoleInputW(IntPtr input, KeyEventRecord[] records, uint count, out uint written);
    [DllImport("kernel32.dll")] static extern bool GetNumberOfConsoleInputEvents(IntPtr input, out uint count);
    [DllImport("kernel32.dll")] static extern bool GetConsoleScreenBufferInfo(IntPtr output, out ScreenBufferInfo info);
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode)] static extern bool ReadConsoleOutputCharacterW(IntPtr output, StringBuilder text, uint length, Coord start, out uint read);
    [DllImport("user32.dll", CharSet = CharSet.Unicode)] static extern short VkKeyScanW(char ch);
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern IntPtr CommandLineToArgvW(string commandLine, out int count);
    [DllImport("kernel32.dll")] static extern IntPtr LocalFree(IntPtr memory);

    const uint CtrlCEvent = 0, Synchronize = 0x00100000, WaitObject0 = 0;
    const uint GenericReadWrite = 0xC0000000, FileShareReadWrite = 3, OpenExisting = 3;
    const ushort KeyEvent = 1, VkBack = 0x08, VkReturn = 0x0D;
    const uint ShiftPressed = 0x10;
    static readonly IntPtr InvalidHandle = new IntPtr(-1);

    // The shell echoing this key is the proof that it reads input. It must be on the keyboard layout,
    // since keys are synthesized from it (a character outside the layout echoes as another one), and
    // must differ from the prompt's last character; prompts end with a space by convention.
    const char Probe = '#';
    const int ShellReadyTimeoutMs = 30000, ProbeIntervalMs = 1000, PollMs = 50;

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    struct StartupInfo
    {
        public int Size;
        public string Reserved, Desktop, Title;
        public int X, Y, XSize, YSize, XCountChars, YCountChars, FillAttribute, Flags;
        public short ShowWindow, Reserved2;
        public IntPtr Reserved3, StdInput, StdOutput, StdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct ProcessInformation { public IntPtr Process, Thread; public int ProcessId, ThreadId; }

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    static extern bool CreateProcessW(string application, StringBuilder commandLine, IntPtr processAttributes, IntPtr threadAttributes,
        bool inheritHandles, uint creationFlags, IntPtr environment, string currentDirectory, ref StartupInfo startup, out ProcessInformation info);

    const uint CreateNoWindow = 0x08000000;

    // Starts a process on a console that has no window: no window can take the user's focus, which a
    // hidden console window still does when Windows Terminal is the default terminal. No handles are
    // inherited, so the caller's output pipes close when the caller exits. Returns the process id.
    public static int StartWithoutWindow(string commandLine)
    {
        var startup = new StartupInfo { Size = Marshal.SizeOf(typeof(StartupInfo)) };
        ProcessInformation info;
        if (!CreateProcessW(null, new StringBuilder(commandLine), IntPtr.Zero, IntPtr.Zero, false, CreateNoWindow, IntPtr.Zero, null, ref startup, out info))
            throw new System.ComponentModel.Win32Exception();
        CloseHandle(info.Thread);
        CloseHandle(info.Process);
        return info.ProcessId;
    }

    // Same splitting rules the C runtime applies, so the result is the argv the agent received.
    public static string[] SplitCommandLine(string commandLine)
    {
        int count;
        IntPtr argv = CommandLineToArgvW(commandLine, out count);
        try
        {
            var args = new string[count];
            for (int i = 0; i < count; i++)
                args[i] = Marshal.PtrToStringUni(Marshal.ReadIntPtr(argv, i * IntPtr.Size));
            return args;
        }
        finally { LocalFree(argv); }
    }

    // Exits the agent gracefully, then types relaunchLine, unless null or empty, into the shell that launched it.
    // Each Ctrl+C advances the agent one step toward exit (cancel the turn, clear input, confirm),
    // so presses repeat, pressIntervalMs apart, until it exits or maxPresses have been sent.
    // afterExit, unless null, runs between the exit and the relaunch, when the agent can no longer
    // overwrite state it holds in memory. It runs attached to the exited agent's console, so it must
    // not write to the host (the reason below) nor start a process: creating one fails there with
    // "The handle is invalid".
    // Returns detached from every console: the PowerShell host still holds handles of its
    // original console, and any host output while attached elsewhere fails on the user's screen.
    public static RestartResult Restart(uint agentPid, string relaunchLine, int maxPresses, int pressIntervalMs, Action afterExit)
    {
        IntPtr agent = OpenProcess(Synchronize, false, agentPid);
        FreeConsole();
        try
        {
            if (!AttachConsole(agentPid)) return RestartResult.AttachFailed;
            SetConsoleCtrlIgnore(IntPtr.Zero, true);
            bool exited = false;
            for (int i = 0; i < maxPresses && !exited; i++)
            {
                GenerateConsoleCtrlEvent(CtrlCEvent, 0);
                exited = WaitForSingleObject(agent, (uint)pressIntervalMs) == WaitObject0;
            }
            if (!exited && WaitForSingleObject(agent, 15000) != WaitObject0) return RestartResult.StillRunning;
            // PowerShell passes $null to a string parameter as "", so both mean "no relaunch".
            if (string.IsNullOrEmpty(relaunchLine)) return RestartResult.Exited;
            if (afterExit != null) afterExit();
            return TypeIntoReadingShell(relaunchLine);
        }
        finally
        {
            FreeConsole();
            CloseHandle(agent);
        }
    }

    // Input written while the shell is still returning to its prompt can be discarded, and nothing
    // outside the shell can see when that window closes. A line editor echoes only keys it has read,
    // so the line is sent once, only after a probe key has been echoed; probes are harmless if lost.
    static RestartResult TypeIntoReadingShell(string line)
    {
        IntPtr input = CreateFileW("CONIN$", GenericReadWrite, FileShareReadWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
        IntPtr output = CreateFileW("CONOUT$", GenericReadWrite, FileShareReadWrite, IntPtr.Zero, OpenExisting, 0, IntPtr.Zero);
        try
        {
            if (input == InvalidHandle || output == InvalidHandle) return RestartResult.InputFailed;
            int echoed = AwaitProbeEcho(input, output);
            if (echoed < 0) return RestartResult.ShellNotReading;
            return WriteKeys(input, new string('\b', echoed) + line + "\r") ? RestartResult.Relaunched : RestartResult.InputFailed;
        }
        finally
        {
            CloseHandle(input);
            CloseHandle(output);
        }
    }

    // Returns how many probes the shell echoed (to be erased), or -1 if it never read one in time.
    static int AwaitProbeEcho(IntPtr input, IntPtr output)
    {
        int sent = 0;
        for (long deadline = Environment.TickCount64 + ShellReadyTimeoutMs; Environment.TickCount64 < deadline;)
        {
            if (!WriteKeys(input, Probe.ToString())) return -1;
            sent++;
            for (long next = Environment.TickCount64 + ProbeIntervalMs; Environment.TickCount64 < next; Thread.Sleep(PollMs))
            {
                if (TrailingProbes(output, 1) == 0) continue;
                // The shell now reads; let it drain every probe still queued, then count what it echoed.
                uint pending;
                while (GetNumberOfConsoleInputEvents(input, out pending) && pending > 0) Thread.Sleep(PollMs);
                return TrailingProbes(output, sent);
            }
        }
        return -1;
    }

    // Number of consecutive probe characters immediately before the cursor, looking back at most max cells.
    static int TrailingProbes(IntPtr output, int max)
    {
        ScreenBufferInfo info;
        if (!GetConsoleScreenBufferInfo(output, out info)) return 0;
        int cursor = info.Cursor.Y * info.Size.X + info.Cursor.X;
        int length = Math.Min(max, cursor);
        int first = cursor - length;
        var start = new Coord { X = (short)(first % info.Size.X), Y = (short)(first / info.Size.X) };
        var text = new StringBuilder(length);
        uint read;
        if (length == 0 || !ReadConsoleOutputCharacterW(output, text, (uint)length, start, out read)) return 0;
        int count = 0;
        for (int i = (int)read - 1; i >= 0 && text[i] == Probe; i--) count++;
        return count;
    }

    static bool WriteKeys(IntPtr input, string keys)
    {
        var records = new KeyEventRecord[keys.Length * 2];
        for (int i = 0; i < keys.Length; i++)
        {
            char ch = keys[i];
            short scan = VkKeyScanW(ch);
            ushort vk = ch == '\r' ? VkReturn : ch == '\b' ? VkBack : (ushort)(scan & 0xFF);
            uint state = scan != -1 && ((scan >> 8) & 1) != 0 ? ShiftPressed : 0;
            for (int up = 0; up < 2; up++)
                records[i * 2 + up] = new KeyEventRecord
                {
                    EventType = KeyEvent, KeyDown = up == 0 ? 1 : 0, RepeatCount = 1,
                    VirtualKeyCode = vk, UnicodeChar = ch, ControlKeyState = state,
                };
        }
        uint written;
        return WriteConsoleInputW(input, records, (uint)records.Length, out written) && written == records.Length;
    }
}
