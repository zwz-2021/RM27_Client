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
    public static extern IntPtr SetThreadDpiAwarenessContext(IntPtr context);
'@

function Save-PreviewCapture([IntPtr]$Handle, $Surface, [string]$Destination) {
    # UI Automation supplies physical screen coordinates even on a scaled display.
    $oldContext = [RM27.PreviewCapture]::SetThreadDpiAwarenessContext([IntPtr](-4))
    $window = $graphics = $preview = $null
    try {
        $bounds = New-Object 'RM27.PreviewCapture+Rect'
        if (-not [RM27.PreviewCapture]::GetWindowRect($Handle, [ref]$bounds)) { throw 'No HWND bounds' }
        $window = [Drawing.Bitmap]::new($bounds.Right - $bounds.Left, $bounds.Bottom - $bounds.Top)
        $graphics = [Drawing.Graphics]::FromImage($window)
        $dc = $graphics.GetHdc()
        try {
            if (-not [RM27.PreviewCapture]::PrintWindow($Handle, $dc, 2)) { throw 'Window capture failed' }
        } finally { $graphics.ReleaseHdc($dc) }

        $rect = [Drawing.Rectangle]::new([Math]::Round($Surface.X - $bounds.Left),
            [Math]::Round($Surface.Y - $bounds.Top), [Math]::Round($Surface.Width), [Math]::Round($Surface.Height))
        $preview = $window.Clone($rect, $window.PixelFormat)
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
