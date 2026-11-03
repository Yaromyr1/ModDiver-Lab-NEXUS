using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Threading;
using System.Runtime.InteropServices;
using System.Windows.Forms;
using System.IO;
using System.Reflection;

public static class ModDiverLoading
{
    public static string AssetDirectory;
    private static Stream Asset(string resource, string filename)
    {
        Stream embedded = Assembly.GetExecutingAssembly().GetManifestResourceStream(resource);
        if (embedded != null) return embedded;
        string path = Path.Combine(AssetDirectory ?? AppDomain.CurrentDomain.BaseDirectory, filename);
        return File.Exists(path) ? File.OpenRead(path) : null;
    }
    private static Thread thread;
    private static Form form;
    private static readonly ManualResetEvent ready = new ManualResetEvent(false);
    [DllImport("dwmapi.dll")]
    private static extern int DwmSetWindowAttribute(IntPtr hwnd, int attribute, ref int value, int size);
    [DllImport("user32.dll")]
    private static extern bool ReleaseCapture();
    [DllImport("user32.dll")]
    private static extern IntPtr SendMessage(IntPtr hwnd, int message, IntPtr wParam, IntPtr lParam);

    private static void AddCaptionFallback(Form window, Color background, Color text)
    {
        window.FormBorderStyle = FormBorderStyle.None;
        window.ClientSize = new Size(440, 160);
        Label header = new Label();
        header.Name = "ThemeCaption";
        header.Text = window.Text;
        header.Dock = DockStyle.Top;
        header.Height = 30;
        header.Padding = new Padding(12, 0, 0, 0);
        header.TextAlign = ContentAlignment.MiddleLeft;
        header.BackColor = background;
        header.ForeColor = text;
        header.MouseDown += delegate(object sender, MouseEventArgs args)
        {
            if (args.Button != MouseButtons.Left) return;
            ReleaseCapture();
            SendMessage(window.Handle, 0xA1, new IntPtr(2), IntPtr.Zero);
        };
        window.Controls.Add(header);
    }

    public static void Show(string background)
    {
        Show(background, background, null);
    }
    public static void Show(string background, string caption, string captionText)
    {
        Show(background, caption, captionText, "#ffd400");
    }
    public static void Show(string background, string caption, string captionText, string secondary)
    {
        if (thread != null) return;
        ready.Reset();
        thread = new Thread(delegate()
        {
            try
            {
                Color bg = ColorTranslator.FromHtml(background);
                form = new Form();
                form.Text = "ModDiver Laboratory";
                form.ClientSize = new Size(500, 190);
                form.StartPosition = FormStartPosition.Manual;
                Rectangle area = Screen.PrimaryScreen == null ? Screen.GetWorkingArea(Cursor.Position) : Screen.PrimaryScreen.WorkingArea;
                form.Location = new Point(area.Left + Math.Max(0, (area.Width - form.Width) / 2),
                    area.Top + Math.Max(0, (area.Height - form.Height) / 2));
                form.FormBorderStyle = FormBorderStyle.None;
                form.ControlBox = false;
                form.TopMost = true;
                form.BackColor = bg;
                using (Stream icon = Asset("moddiver-icon.ico", "icon.ico"))
                    if (icon != null) using (Icon loaded = new Icon(icon)) form.Icon = (Icon)loaded.Clone();
                form.Controls.Add(new LoadingPanel(bg, ColorTranslator.FromHtml(String.IsNullOrEmpty(secondary) ? "#ffd400" : secondary)));
                bool customCaption = false;
                bool stylingCaption = false;
                Action styleCaption = delegate
                {
                    if (customCaption) return;
                    stylingCaption = true;
                    Color title = ColorTranslator.FromHtml(caption ?? background);
                    Color text = captionText == null ? (title.GetBrightness() < .5f ? Color.White : Color.Black)
                        : ColorTranslator.FromHtml(captionText);
                    bool supported = false;
                    try
                    {
                        int dark = title.GetBrightness() < .5f ? 1 : 0;
                        int titleColor = ColorTranslator.ToWin32(title);
                        int textColor = ColorTranslator.ToWin32(text);
                        DwmSetWindowAttribute(form.Handle, 20, ref dark, 4);
                        supported = DwmSetWindowAttribute(form.Handle, 35, ref titleColor, 4) == 0;
                        DwmSetWindowAttribute(form.Handle, 34, ref titleColor, 4);
                        DwmSetWindowAttribute(form.Handle, 36, ref textColor, 4);
                    }
                    catch (DllNotFoundException) { }
                    catch (EntryPointNotFoundException) { }
                    if (!supported)
                    {
                        customCaption = true;
                        AddCaptionFallback(form, title, text);
                    }
                    stylingCaption = false;
                };
                form.HandleCreated += delegate { form.BeginInvoke(styleCaption); };
                form.Shown += delegate { if (!stylingCaption) { styleCaption(); ready.Set(); } };
                Application.Run(form);
            }
            finally { ready.Set(); }
        });
        thread.IsBackground = true;
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        ready.WaitOne(5000);
    }
    public static void Close()
    {
        if (form != null && form.IsHandleCreated && !form.IsDisposed)
            try { form.BeginInvoke((Action)delegate { form.Close(); }); } catch { }
        if (thread != null) thread.Join(2000);
        thread = null;
        form = null;
    }
    private sealed class LoadingPanel : Panel
    {
        private static double Luminance(Color color)
        {
            double[] values = {color.R/255.0,color.G/255.0,color.B/255.0};
            for (int i=0;i<3;i++) values[i] = values[i] <= .04045 ? values[i]/12.92 : Math.Pow((values[i]+.055)/1.055,2.4);
            return values[0]*.2126+values[1]*.7152+values[2]*.0722;
        }
        private static double Contrast(Color a,Color b)
        {
            double x=Luminance(a),y=Luminance(b);
            return (Math.Max(x,y)+.05)/(Math.Min(x,y)+.05);
        }
        private static Color EnsureVisible(Color color,Color background,double minimum)
        {
            if (Contrast(color,background)>=minimum) return color;
            Color target=Luminance(background)<.179?Color.White:Color.Black;
            for(int step=1;step<=20;step++)
            {
                double amount=step/20.0;
                Color value=Color.FromArgb((int)(color.R*(1-amount)+target.R*amount),
                    (int)(color.G*(1-amount)+target.G*amount),(int)(color.B*(1-amount)+target.B*amount));
                if(Contrast(value,background)>=minimum)return value;
            }
            return target;
        }
        private int phase;
        private readonly System.Windows.Forms.Timer timer;
        private readonly Color secondary;
        private readonly Color surface;
        private readonly Color outline;
        public LoadingPanel(Color background, Color secondary)
        {
            this.secondary = EnsureVisible(secondary, background, 3);
            bool light = Luminance(background) >= .179;
            Color ink = light ? Color.FromArgb(24, 28, 35) : Color.FromArgb(245, 247, 250);
            surface = Color.FromArgb((background.R * 9 + ink.R) / 10,
                (background.G * 9 + ink.G) / 10, (background.B * 9 + ink.B) / 10);
            outline = Color.FromArgb((background.R * 3 + ink.R) / 4,
                (background.G * 3 + ink.G) / 4, (background.B * 3 + ink.B) / 4);
            Dock = DockStyle.Fill;
            BackColor = surface;
            DoubleBuffered = true;
            timer = new System.Windows.Forms.Timer();
            timer.Interval = 35;
            timer.Tick += delegate { phase = (phase + 7) % 480; Invalidate(); };
            timer.Start();
        }
        protected override void OnPaint(PaintEventArgs e)
        {
            base.OnPaint(e);
            e.Graphics.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            Rectangle bounds = ClientRectangle;
            bounds.Width--; bounds.Height--;
            using (Pen edge = new Pen(outline)) e.Graphics.DrawRectangle(edge, bounds);
            using (Brush stripe = new SolidBrush(secondary)) e.Graphics.FillRectangle(stripe, 1, 1, Width - 2, 3);
            using (Font font = new Font("Segoe UI Semibold", 10, FontStyle.Bold))
            using (Brush titleInk = new SolidBrush(secondary))
            using (Pen pen = new Pen(secondary, 1.8f))
            {
                const string title = "MODDIVER LABORATORY";
                SizeF size = e.Graphics.MeasureString(title, font);
                float x = 30;
                e.Graphics.DrawString(title, font, titleInk, x, 23);
                float fx = x + size.Width + 9, fy = 24;
                e.Graphics.DrawLines(pen, new PointF[] {
                    new PointF(fx+7, fy), new PointF(fx+7, fy+8),
                    new PointF(fx+1, fy+20), new PointF(fx+20, fy+20),
                    new PointF(fx+13, fy+8), new PointF(fx+13, fy) });
                e.Graphics.DrawLine(pen, fx+5, fy, fx+15, fy);
                e.Graphics.DrawLine(pen, fx+4, fy+14, fx+17, fy+14);
                e.Graphics.DrawEllipse(pen, fx+8, fy+16, 2, 2);
            }
            int left = 30, right = Width - 30, y = 148;
            bool light = Luminance(surface) >= .179;
            Color ink = light ? Color.FromArgb(24, 28, 35) : Color.FromArgb(245, 247, 250);
            Color muted = EnsureVisible(light ? Color.FromArgb(65, 73, 87) : Color.FromArgb(195, 203, 215),surface,4.5);
            Color trackColor = light ? Color.FromArgb(205, 210, 218) : Color.FromArgb(49, 55, 65);
            Color accent = secondary;

            using (Font heading = new Font("Segoe UI Semibold", 15, FontStyle.Bold))
                TextRenderer.DrawText(e.Graphics, "Preparing your workspace", heading,
                    new Rectangle(left, 58, right - left, 28), ink,
                    TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding);
            using (Font description = new Font("Segoe UI", 9, FontStyle.Regular))
                TextRenderer.DrawText(e.Graphics, "Loading your tools and checking your setup", description,
                    new Rectangle(left, 90, right - left, 20), muted,
                    TextFormatFlags.Left | TextFormatFlags.VerticalCenter | TextFormatFlags.NoPadding);

            using (Pen track = new Pen(trackColor, 14))
            {
                track.StartCap = track.EndCap = LineCap.Round;
                e.Graphics.DrawLine(track, left, y, right, y);
            }
            float position = (float)((1 - Math.Cos(phase * Math.PI * 2 / 480)) / 2);
            float span = (right - left) * .24f;
            float sampleX = left + position * (right - left - span);
            using (Pen halo = new Pen(Color.FromArgb((trackColor.R*2+accent.R)/3,
                (trackColor.G*2+accent.G)/3,(trackColor.B*2+accent.B)/3),14))
            {
                halo.StartCap = halo.EndCap = LineCap.Round;
                e.Graphics.DrawLine(halo,sampleX,y,sampleX+span,y);
            }
            using (LinearGradientBrush gradient = new LinearGradientBrush(
                new PointF(sampleX,y-4),new PointF(sampleX+span,y+4),accent,ink))
            using (Pen sample = new Pen(gradient,8))
            {
                sample.StartCap = sample.EndCap = LineCap.Round;
                e.Graphics.DrawLine(sample,sampleX,y,sampleX+span,y);
            }
            Rectangle label = new Rectangle(left, 119, right-left, 20);
            using (Font status = new Font(SystemFonts.MessageBoxFont,FontStyle.Bold))
                TextRenderer.DrawText(e.Graphics, "STARTING", status, label,
                    ink, TextFormatFlags.Right | TextFormatFlags.VerticalCenter);
        }
        protected override void Dispose(bool disposing)
        {
            if (disposing) timer.Dispose();
            base.Dispose(disposing);
        }
    }
}
