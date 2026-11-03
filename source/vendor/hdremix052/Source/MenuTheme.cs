// SPDX-License-Identifier: GPL-3.0-only
// Visual palette matched to the user-supplied farm configurator reference.
using System;
using System.Drawing;
using System.Windows.Forms;
namespace HDRemix.LunaCosmetics {
    internal static class MenuTheme {
        internal static readonly Color Background=ColorTranslator.FromHtml("#0B0D0F"),Panel=ColorTranslator.FromHtml("#171A1E"),
            Accent=ColorTranslator.FromHtml("#FFE600"),Text=ColorTranslator.FromHtml("#F1F1DF"),
            Muted=ColorTranslator.FromHtml("#B8BAB5"),Border=ColorTranslator.FromHtml("#41443C");
        internal static void Button(Button button,bool primary=false){
            button.FlatStyle=FlatStyle.Flat;button.UseVisualStyleBackColor=false;
            button.BackColor=primary?Accent:Panel;button.ForeColor=primary?Background:Accent;
            button.FlatAppearance.BorderColor=primary?Accent:Border;
            button.FlatAppearance.MouseOverBackColor=ColorTranslator.FromHtml(primary?"#FFF276":"#2D3031");
            button.FlatAppearance.MouseDownBackColor=ColorTranslator.FromHtml(primary?"#DCC900":"#34382D");
            button.Font=new Font("Segoe UI",primary?11:10,primary?FontStyle.Bold:FontStyle.Regular);button.Cursor=Cursors.Hand;
        }
        internal static void Combo(ComboBox combo){
            combo.BackColor=Panel;combo.ForeColor=Text;combo.FlatStyle=FlatStyle.Flat;combo.DrawMode=DrawMode.OwnerDrawFixed;combo.ItemHeight=24;
            combo.DrawItem+=delegate(object sender,DrawItemEventArgs e){
                if(e.Index<0)return;bool selected=(e.State&DrawItemState.Selected)!=0&&(e.State&DrawItemState.ComboBoxEdit)==0;
                using(var brush=new SolidBrush(selected?Accent:Panel))e.Graphics.FillRectangle(brush,e.Bounds);
                TextRenderer.DrawText(e.Graphics,Convert.ToString(combo.Items[e.Index]),combo.Font,e.Bounds,combo.Enabled?(selected?Background:Text):Muted,TextFormatFlags.VerticalCenter|TextFormatFlags.Left|TextFormatFlags.EndEllipsis);
                if((e.State&DrawItemState.Focus)!=0)e.DrawFocusRectangle();
            };
        }
    }
    internal sealed class ThemeGroupBox:GroupBox {
        internal ThemeGroupBox(){SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);}
        protected override void OnPaint(PaintEventArgs e){
            e.Graphics.Clear(BackColor);int y=Font.Height/2;
            using(var pen=new Pen(MenuTheme.Border))e.Graphics.DrawRectangle(pen,0,y,Width-1,Height-y-1);
            int titleWidth=Math.Min(Width-20,TextRenderer.MeasureText(Text,Font).Width+8);
            using(var bg=new SolidBrush(BackColor))e.Graphics.FillRectangle(bg,8,0,titleWidth,Font.Height+2);
            TextRenderer.DrawText(e.Graphics,Text,Font,new Rectangle(10,0,titleWidth,Font.Height+2),MenuTheme.Accent,TextFormatFlags.Left|TextFormatFlags.VerticalCenter|TextFormatFlags.EndEllipsis);
        }
    }
    internal sealed class ThemeComboBox:ComboBox {
        protected override void WndProc(ref Message m){
            base.WndProc(ref m);
            // Paint only this UI control's frame/arrow. The native ComboBox still
            // owns keyboard navigation, accessibility and its dropdown list.
            if(m.Msg==0x000f||((m.Msg==0x0317||m.Msg==0x0318)&&m.WParam!=IntPtr.Zero)){
                using(var g=m.Msg==0x000f?Graphics.FromHwnd(Handle):Graphics.FromHdc(m.WParam)){
                    int button=Math.Min(Height-2,SystemInformation.VerticalScrollBarWidth+7);int left=Width-button-1;
                    using(var fill=new SolidBrush(MenuTheme.Panel))g.FillRectangle(fill,left,1,button,Height-2);
                    using(var edge=new Pen(MenuTheme.Border))g.DrawRectangle(edge,0,0,Width-1,Height-1);
                    int x=left+button/2,y=Height/2;
                    using(var arrow=new SolidBrush(Enabled?MenuTheme.Accent:MenuTheme.Muted))g.FillPolygon(arrow,new[]{new Point(x-4,y-2),new Point(x+4,y-2),new Point(x,y+3)});
                }
            }
        }
    }
    internal sealed class ThemeCheckBox:CheckBox {
        bool hover;
        internal ThemeCheckBox(){SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);BackColor=MenuTheme.Background;ForeColor=MenuTheme.Text;Cursor=Cursors.Hand;AccessibleRole=AccessibleRole.CheckButton;}
        protected override void OnMouseEnter(EventArgs e){hover=true;Invalidate();base.OnMouseEnter(e);}
        protected override void OnMouseLeave(EventArgs e){hover=false;Invalidate();base.OnMouseLeave(e);}
        protected override void OnCheckedChanged(EventArgs e){Invalidate();base.OnCheckedChanged(e);}
        protected override void OnEnabledChanged(EventArgs e){Invalidate();base.OnEnabledChanged(e);}
        protected override void OnPaint(PaintEventArgs e){
            e.Graphics.Clear(BackColor);int side=Math.Max(14,(int)(Font.Height*0.9));int top=(Height-side)/2;var box=new Rectangle(2,top,side,side);
            using(var fill=new SolidBrush(Checked&&Enabled?MenuTheme.Accent:MenuTheme.Panel))e.Graphics.FillRectangle(fill,box);
            using(var edge=new Pen(Enabled&&(hover||Focused||Checked)?MenuTheme.Accent:MenuTheme.Border))e.Graphics.DrawRectangle(edge,box);
            if(Checked){using(var tick=new Pen(Enabled?MenuTheme.Background:MenuTheme.Muted,2)){e.Graphics.DrawLines(tick,new[]{new Point(box.Left+3,box.Top+side/2),new Point(box.Left+side/2-1,box.Bottom-4),new Point(box.Right-3,box.Top+4)});}}
            var text=new Rectangle(side+13,0,Width-side-17,Height);TextRenderer.DrawText(e.Graphics,Text,Font,text,Enabled?(hover?MenuTheme.Accent:MenuTheme.Text):MenuTheme.Muted,TextFormatFlags.VerticalCenter|TextFormatFlags.SingleLine|TextFormatFlags.EndEllipsis);
            if(Focused&&ShowFocusCues)ControlPaint.DrawFocusRectangle(e.Graphics,text,MenuTheme.Accent,BackColor);
        }
    }
    internal sealed class ThemeProgress:Control {
        int value;
        internal int Value {get{return value;}set{this.value=Math.Max(0,Math.Min(100,value));Invalidate();}}
        internal ThemeProgress(){SetStyle(ControlStyles.UserPaint|ControlStyles.AllPaintingInWmPaint|ControlStyles.OptimizedDoubleBuffer,true);TabStop=false;}
        protected override void OnPaint(PaintEventArgs e){e.Graphics.Clear(MenuTheme.Border);var rect=new Rectangle(1,1,Math.Max(0,Width-2),Math.Max(0,Height-2));using(var bg=new SolidBrush(MenuTheme.Panel))e.Graphics.FillRectangle(bg,rect);rect.Width=rect.Width*value/100;using(var fill=new SolidBrush(MenuTheme.Accent))e.Graphics.FillRectangle(fill,rect);}
    }
}
