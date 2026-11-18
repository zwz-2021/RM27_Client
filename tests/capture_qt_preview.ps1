#requires -Version 5.1
# Capture only the test process's HWND and save only the accessible preview region.
Add-Type -AssemblyName System.Drawing
Add-Type -Namespace RM27 -Name PreviewCapture -MemberDefinition @'
    [System.Runtime.InteropServices.StructLayout(System.Runtime.InteropServices.LayoutKind.Sequential)]
    public struct Rect { public int Left, Top, Right, Bottom; }
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdc, uint flags);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hwnd, out Rect rect);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool IsIconic(IntPtr hwnd);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern bool ShowWindowAsync(IntPtr hwnd, int command);
    [System.Runtime.InteropServices.DllImport("user32.dll")]
    public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
'@

function Save-PreviewCapture([IntPtr]$Handle, [string]$Destination) {
    # UI Automation supplies physical screen coordinates even on a scaled display.
    $oldContext = [RM27.PreviewCapture]::SetThreadDpiAwarenessContext([IntPtr](-4))
    $window = $graphics = $preview = $null
    try {
        $bounds = New-Object 'RM27.PreviewCapture+Rect'
        $timer = [Diagnostics.Stopwatch]::StartNew()
        while ($true) {
            # A minimized HWND has only a taskbar-sized rectangle. Restore this test's window.
            if ([RM27.PreviewCapture]::IsIconic($Handle)) {
                [void][RM27.PreviewCapture]::ShowWindowAsync($Handle, 9) # SW_RESTORE
            }
            # Qt can replace or reposition the preview when switching back to the workbench.
            $area = $null
            try {
                $surface = (Get-Controls)['videoPreviewSurface']
                if ($surface -and -not $surface.Current.IsOffscreen) { $area = $surface.Current.BoundingRectangle }
            } catch [System.Windows.Automation.ElementNotAvailableException], [Runtime.InteropServices.COMException] {
                # Query the replacement element on the next iteration.
            }
            if (-not [RM27.PreviewCapture]::GetWindowRect($Handle, [ref]$bounds)) { throw 'No HWND bounds' }
            $width = $bounds.Right - $bounds.Left
            $height = $bounds.Bottom - $bounds.Top
            if ($area -and -not $area.IsEmpty -and $area.Width -gt 0 -and $area.Height -gt 0) {
                $rect = [Drawing.Rectangle]::new([Math]::Round($area.X - $bounds.Left),
                    [Math]::Round($area.Y - $bounds.Top), [Math]::Round($area.Width), [Math]::Round($area.Height))
                if ($rect.X -ge 0 -and $rect.Y -ge 0 -and $rect.Width -gt 0 -and $rect.Height -gt 0 -and
                    $rect.Right -le $width -and $rect.Bottom -le $height) { break }
            }
            if ($timer.Elapsed.TotalSeconds -ge 2) {
                throw "Preview not fully visible in test window: surface='$area', HWND=($($bounds.Left),$($bounds.Top),$width,$height)."
            }
            Start-Sleep -Milliseconds 40
        }
        $window = [Drawing.Bitmap]::new($width, $height)
        $graphics = [Drawing.Graphics]::FromImage($window)
        $dc = $graphics.GetHdc()
        try {
            if (-not [RM27.PreviewCapture]::PrintWindow($Handle, $dc, 2)) { throw 'Window capture failed' }
        } finally { $graphics.ReleaseHdc($dc) }

        try { $preview = $window.Clone($rect, $window.PixelFormat) }
        catch { throw "Preview capture failed for $rect on ${width}x${height}: $($_.Exception.Message)" }
        $preview.Save($Destination, [Drawing.Imaging.ImageFormat]::Png)
        # Sample inside the fitted 16:9 picture, away from status text and edges.
        $width = [Math]::Min($rect.Width, $rect.Height * 16 / 9)
        $height = $width * 9 / 16
        $samples = foreach ($v in @(0.3, 0.7)) {
            foreach ($u in @(0.3, 0.7)) {
                $x = [int](($rect.Width - $width) / 2 + $u * $width)
                $y = [int](($rect.Height - $height) / 2 + $v * $height)
                $pixel = $preview.GetPixel($x, $y)
                ,@([int]$pixel.R, [int]$pixel.G, [int]$pixel.B)
            }
        }
        $margin = @()
        if (($rect.Width - $width) / 2 -gt 10) {
            $x = [int](($rect.Width - $width) / 2 - 5)
            $pixel = $preview.GetPixel($x, [int]($rect.Height / 2))
            $margin = @([int]$pixel.R, [int]$pixel.G, [int]$pixel.B)
        }
        return @{ width = $rect.Width; height = $rect.Height; rgb = $samples; sideMargin = $margin }
    } finally {
        if ($preview) { $preview.Dispose() }
        if ($graphics) { $graphics.Dispose() }
        if ($window) { $window.Dispose() }
        [void][RM27.PreviewCapture]::SetThreadDpiAwarenessContext($oldContext)
    }
}
