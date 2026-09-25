#!/usr/bin/env python3
"""
VOICEVOX 自動ボイス生成ツール
テキストファイルの各行を読み込み、選択したキャラクターで音声を自動生成します。
"""

import customtkinter as ctk
from tkinter import filedialog, messagebox
import requests
import threading
import os
import io
from pathlib import Path
from typing import Optional

# ==================== 設定 ====================
DEFAULT_HOST = "http://127.0.0.1:50021"
DEFAULT_SPEAKER_ID = 3  # ずんだもん ノーマル
DEFAULT_BASE_NAME = "Sample"
DEFAULT_EXTENSION = "wav"
TIMEOUT = 30

# 対応拡張子（VOICEVOXはWAVのみ返すため、他は変換）
SUPPORTED_EXTENSIONS = ["wav", "ogg", "mp3", "flac", "m4a"]

# ==================== テーマ設定 ====================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


class VoiceVoxClient:
    """VOICEVOX Engine API クライアント"""

    def __init__(self, base_url: str = DEFAULT_HOST):
        self.base_url = base_url.rstrip("/")
        self.speakers_cache: list = []
        self.speaker_map: dict = {}  # "キャラ名 (スタイル)" -> id

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/version", timeout=3)
            return r.status_code == 200
        except Exception:
            return False

    def fetch_speakers(self) -> list:
        """スピーカー一覧を取得し、ドロップダウン用リストを作成"""
        try:
            r = requests.get(f"{self.base_url}/speakers", timeout=TIMEOUT)
            r.raise_for_status()
            speakers = r.json()
            self.speakers_cache = speakers
            self.speaker_map = {}
            options = []

            for sp in speakers:
                name = sp.get("name", "不明")
                for style in sp.get("styles", []):
                    style_name = style.get("name", "ノーマル")
                    style_id = style.get("id")
                    label = f"{name} ({style_name})"
                    self.speaker_map[label] = style_id
                    options.append(label)

            # ずんだもんを先頭に寄せる
            zunda = [o for o in options if "ずんだもん" in o]
            others = [o for o in options if "ずんだもん" not in o]
            return zunda + others
        except Exception as e:
            print(f"スピーカー取得エラー: {e}")
            return []

    def synthesize(self, text: str, speaker_id: int) -> Optional[bytes]:
        """テキストから音声を合成してWAVバイナリを返す"""
        if not text.strip():
            return None
        try:
            # 1. audio_query
            query_resp = requests.post(
                f"{self.base_url}/audio_query",
                params={"text": text, "speaker": speaker_id},
                timeout=TIMEOUT,
            )
            query_resp.raise_for_status()
            query = query_resp.json()

            # 2. synthesis
            synth_resp = requests.post(
                f"{self.base_url}/synthesis",
                params={"speaker": speaker_id},
                json=query,
                timeout=TIMEOUT,
            )
            synth_resp.raise_for_status()
            return synth_resp.content
        except Exception as e:
            print(f"合成エラー (speaker={speaker_id}): {e}")
            return None


def convert_wav_bytes(wav_bytes: bytes, fmt: str) -> Optional[bytes]:
    """WAVバイナリを指定フォーマットに変換して返す。wavならそのまま返す。"""
    fmt = fmt.lower().lstrip(".")
    if fmt == "wav":
        return wav_bytes
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(io.BytesIO(wav_bytes), format="wav")
        buf = io.BytesIO()
        # 一部形式は codec 指定が必要
        export_kwargs = {"format": fmt}
        if fmt == "ogg":
            export_kwargs["codec"] = "libvorbis"
        elif fmt == "mp3":
            export_kwargs["bitrate"] = "192k"
        elif fmt == "m4a":
            export_kwargs["format"] = "ipod"  # m4a/aac
            export_kwargs["codec"] = "aac"
        audio.export(buf, **export_kwargs)
        return buf.getvalue()
    except Exception as e:
        print(f"変換エラー ({fmt}): {e}")
        return None


class LineRow(ctk.CTkFrame):
    """各行のテキスト + キャラ選択ドロップダウン"""

    def __init__(self, master, index: int, text: str, speaker_options: list, default_speaker: str, **kwargs):
        super().__init__(master, **kwargs)
        self.index = index
        self.speaker_var = ctk.StringVar(value=default_speaker)

        # 行番号
        self.idx_label = ctk.CTkLabel(
            self, text=f"{index:03d}", width=40, font=ctk.CTkFont(size=12, weight="bold")
        )
        self.idx_label.pack(side="left", padx=(8, 4), pady=6)

        # テキスト（長すぎる場合は省略表示）
        display_text = text if len(text) <= 60 else text[:57] + "..."
        self.text_label = ctk.CTkLabel(
            self,
            text=display_text,
            anchor="w",
            width=380,
            font=ctk.CTkFont(size=13),
        )
        self.text_label.pack(side="left", padx=4, pady=6, fill="x", expand=True)
        self.full_text = text  # 実際のテキストを保持

        # スピーカー選択
        self.speaker_menu = ctk.CTkOptionMenu(
            self,
            variable=self.speaker_var,
            values=speaker_options if speaker_options else ["ずんだもん (ノーマル)"],
            width=200,
            font=ctk.CTkFont(size=12),
        )
        self.speaker_menu.pack(side="right", padx=(4, 12), pady=6)

    def get_speaker_label(self) -> str:
        return self.speaker_var.get()

    def get_text(self) -> str:
        return self.full_text


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("VOICEVOX 自動ボイス生成ツール")
        self.geometry("920x720")
        self.minsize(800, 600)

        self.client = VoiceVoxClient()
        self.speaker_options: list = []
        self.line_rows: list[LineRow] = []
        self.lines: list[str] = []
        self.is_generating = False

        self._build_ui()
        self.after(100, self._check_engine)

    def _build_ui(self):
        # ===== ヘッダー =====
        header = ctk.CTkFrame(self, corner_radius=0, fg_color=("#1a1a2e", "#0f0f1a"))
        header.pack(fill="x", padx=0, pady=0)

        title = ctk.CTkLabel(
            header,
            text="🎙️  VOICEVOX 自動ボイス生成",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.pack(side="left", padx=20, pady=16)

        self.status_label = ctk.CTkLabel(
            header,
            text="エンジン接続確認中...",
            font=ctk.CTkFont(size=12),
            text_color=("#888", "#aaa"),
        )
        self.status_label.pack(side="right", padx=20, pady=16)

        # ===== 設定エリア =====
        settings = ctk.CTkFrame(self, corner_radius=12)
        settings.pack(fill="x", padx=16, pady=(12, 8))

        # 1行目: テキストファイル
        row1 = ctk.CTkFrame(settings, fg_color="transparent")
        row1.pack(fill="x", padx=12, pady=(12, 6))

        ctk.CTkLabel(row1, text="テキストファイル", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(0, 8)
        )
        self.file_entry = ctk.CTkEntry(row1, placeholder_text="テキストファイルを選択...", width=400)
        self.file_entry.pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkButton(row1, text="参照", width=80, command=self._select_file).pack(side="left", padx=4)

        # 2行目: ベース名 + 拡張子 + 出力フォルダ
        row2 = ctk.CTkFrame(settings, fg_color="transparent")
        row2.pack(fill="x", padx=12, pady=6)

        ctk.CTkLabel(row2, text="ベース名", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(0, 8)
        )
        self.base_name_entry = ctk.CTkEntry(row2, width=120)
        self.base_name_entry.insert(0, DEFAULT_BASE_NAME)
        self.base_name_entry.pack(side="left", padx=4)

        ctk.CTkLabel(row2, text="拡張子", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(16, 8)
        )
        self.ext_var = ctk.StringVar(value=DEFAULT_EXTENSION)
        self.ext_menu = ctk.CTkOptionMenu(
            row2,
            variable=self.ext_var,
            values=SUPPORTED_EXTENSIONS,
            width=90,
            font=ctk.CTkFont(size=13),
        )
        self.ext_menu.pack(side="left", padx=4)

        ctk.CTkLabel(row2, text="出力フォルダ", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(16, 8)
        )
        self.output_entry = ctk.CTkEntry(row2, placeholder_text="出力先フォルダ...", width=240)
        self.output_entry.pack(side="left", padx=4, fill="x", expand=True)
        ctk.CTkButton(row2, text="参照", width=80, command=self._select_output).pack(side="left", padx=4)

        # 3行目: エンジンURL + 再接続
        row3 = ctk.CTkFrame(settings, fg_color="transparent")
        row3.pack(fill="x", padx=12, pady=(6, 12))

        ctk.CTkLabel(row3, text="エンジンURL", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(0, 8)
        )
        self.url_entry = ctk.CTkEntry(row3, width=280)
        self.url_entry.insert(0, DEFAULT_HOST)
        self.url_entry.pack(side="left", padx=4)
        ctk.CTkButton(row3, text="再接続", width=90, command=self._reconnect).pack(side="left", padx=4)

        # ===== 行リスト（スクロール） =====
        list_header = ctk.CTkFrame(self, fg_color="transparent")
        list_header.pack(fill="x", padx=16, pady=(4, 0))

        ctk.CTkLabel(
            list_header,
            text="行番号",
            font=ctk.CTkFont(size=12, weight="bold"),
            width=50,
        ).pack(side="left", padx=(12, 0))
        ctk.CTkLabel(
            list_header,
            text="テキスト",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="left", padx=20)
        ctk.CTkLabel(
            list_header,
            text="キャラクター（デフォルト: ずんだもん）",
            font=ctk.CTkFont(size=12, weight="bold"),
        ).pack(side="right", padx=24)

        self.scroll = ctk.CTkScrollableFrame(self, corner_radius=10)
        self.scroll.pack(fill="both", expand=True, padx=16, pady=8)

        # ===== 下部コントロール =====
        bottom = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        bottom.pack(fill="x", padx=16, pady=(0, 16))

        self.progress = ctk.CTkProgressBar(bottom, height=8)
        self.progress.pack(fill="x", pady=(0, 10))
        self.progress.set(0)

        self.progress_label = ctk.CTkLabel(
            bottom, text="準備完了", font=ctk.CTkFont(size=12), text_color=("#888", "#aaa")
        )
        self.progress_label.pack(anchor="w", pady=(0, 8))

        btn_row = ctk.CTkFrame(bottom, fg_color="transparent")
        btn_row.pack(fill="x")

        self.generate_btn = ctk.CTkButton(
            btn_row,
            text="▶  一括生成",
            font=ctk.CTkFont(size=15, weight="bold"),
            height=42,
            width=180,
            command=self._start_generate,
            state="disabled",
        )
        self.generate_btn.pack(side="left")

        ctk.CTkButton(
            btn_row,
            text="全行をずんだもんに",
            height=36,
            width=160,
            fg_color=("#3a3a4a", "#2a2a3a"),
            hover_color=("#4a4a5a", "#3a3a4a"),
            command=self._set_all_zundamon,
        ).pack(side="left", padx=10)

        self.count_label = ctk.CTkLabel(
            btn_row, text="0 行", font=ctk.CTkFont(size=13), text_color=("#888", "#aaa")
        )
        self.count_label.pack(side="right", padx=8)

    def _check_engine(self):
        self.status_label.configure(text="エンジン接続確認中...", text_color=("#888", "#aaa"))
        threading.Thread(target=self._do_check_engine, daemon=True).start()

    def _do_check_engine(self):
        url = self.url_entry.get().strip() or DEFAULT_HOST
        self.client = VoiceVoxClient(url)
        ok = self.client.is_available()
        if ok:
            options = self.client.fetch_speakers()
            self.speaker_options = options
            default = next((o for o in options if "ずんだもん" in o and "ノーマル" in o), options[0] if options else "ずんだもん (ノーマル)")
            self.after(0, lambda: self._on_engine_ok(default))
        else:
            self.after(0, self._on_engine_fail)

    def _on_engine_ok(self, default_speaker: str):
        self.status_label.configure(
            text="✅ エンジン接続OK",
            text_color=("#2ecc71", "#27ae60"),
        )
        self.generate_btn.configure(state="normal")
        # 既存行があればスピーカーを更新
        for row in self.line_rows:
            row.speaker_menu.configure(values=self.speaker_options)
            if not row.speaker_var.get() or row.speaker_var.get() not in self.speaker_options:
                row.speaker_var.set(default_speaker)

    def _on_engine_fail(self):
        self.status_label.configure(
            text="❌ エンジン未接続（VOICEVOXを起動してください）",
            text_color=("#e74c3c", "#c0392b"),
        )
        self.generate_btn.configure(state="disabled")

    def _reconnect(self):
        self._check_engine()

    def _select_file(self):
        path = filedialog.askopenfilename(
            title="テキストファイルを選択",
            filetypes=[("テキストファイル", "*.txt"), ("すべてのファイル", "*.*")],
        )
        if path:
            self.file_entry.delete(0, "end")
            self.file_entry.insert(0, path)
            self._load_lines(path)

    def _select_output(self):
        path = filedialog.askdirectory(title="出力フォルダを選択")
        if path:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, path)

    def _load_lines(self, path: str):
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = f.read()
        except UnicodeDecodeError:
            with open(path, "r", encoding="cp932") as f:
                raw = f.read()
        except Exception as e:
            messagebox.showerror("エラー", f"ファイル読み込み失敗:\n{e}")
            return

        # 空行を除外しつつ行を取得
        self.lines = [line.strip() for line in raw.splitlines() if line.strip()]
        self._rebuild_rows()

    def _rebuild_rows(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self.line_rows.clear()

        default = next(
            (o for o in self.speaker_options if "ずんだもん" in o and "ノーマル" in o),
            self.speaker_options[0] if self.speaker_options else "ずんだもん (ノーマル)",
        )

        for i, text in enumerate(self.lines):
            row = LineRow(
                self.scroll,
                index=i,
                text=text,
                speaker_options=self.speaker_options,
                default_speaker=default,
                corner_radius=8,
            )
            row.pack(fill="x", pady=3, padx=4)
            self.line_rows.append(row)

        self.count_label.configure(text=f"{len(self.lines)} 行")

    def _set_all_zundamon(self):
        target = next(
            (o for o in self.speaker_options if "ずんだもん" in o and "ノーマル" in o),
            None,
        )
        if not target:
            messagebox.showinfo("情報", "ずんだもんが見つかりません。エンジンに接続してください。")
            return
        for row in self.line_rows:
            row.speaker_var.set(target)

    def _start_generate(self):
        if self.is_generating:
            return
        if not self.lines:
            messagebox.showwarning("警告", "テキストファイルを読み込んでください。")
            return
        if not self.client.is_available():
            messagebox.showerror("エラー", "VOICEVOXエンジンに接続できません。")
            return

        out_dir = self.output_entry.get().strip()
        if not out_dir:
            # テキストファイルと同じフォルダ
            src = self.file_entry.get().strip()
            out_dir = str(Path(src).parent) if src else os.getcwd()
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, out_dir)

        os.makedirs(out_dir, exist_ok=True)
        base = self.base_name_entry.get().strip() or DEFAULT_BASE_NAME
        ext = (self.ext_var.get() or DEFAULT_EXTENSION).lower().lstrip(".")

        # wav以外は pydub + ffmpeg が必要
        if ext != "wav":
            try:
                from pydub import AudioSegment  # noqa: F401
            except ImportError:
                messagebox.showerror(
                    "エラー",
                    "この拡張子への変換には pydub が必要です。\n"
                    "pip install pydub\n"
                    "さらにシステムに ffmpeg がインストールされている必要があります。",
                )
                return

        self.is_generating = True
        self.generate_btn.configure(state="disabled", text="生成中...")
        self.progress.set(0)
        self.progress_label.configure(text="生成を開始します...")

        threading.Thread(
            target=self._do_generate,
            args=(out_dir, base, ext),
            daemon=True,
        ).start()

    def _do_generate(self, out_dir: str, base: str, ext: str):
        total = len(self.line_rows)
        success = 0
        failed = []

        for i, row in enumerate(self.line_rows):
            text = row.get_text()
            label = row.get_speaker_label()
            speaker_id = self.client.speaker_map.get(label, DEFAULT_SPEAKER_ID)

            self.after(
                0,
                lambda i=i, t=total, txt=text[:30]: self.progress_label.configure(
                    text=f"生成中... ({i + 1}/{t})  {txt}..."
                ),
            )
            self.after(0, lambda v=(i + 1) / total: self.progress.set(v))

            wav = self.client.synthesize(text, speaker_id)
            if wav:
                audio_data = convert_wav_bytes(wav, ext)
                if audio_data is None:
                    failed.append(f"{i}: 変換失敗 ({ext})")
                    continue
                filename = f"{base}_{i}.{ext}"
                path = os.path.join(out_dir, filename)
                try:
                    with open(path, "wb") as f:
                        f.write(audio_data)
                    success += 1
                except Exception as e:
                    failed.append(f"{i}: 書き込み失敗 ({e})")
            else:
                failed.append(f"{i}: 合成失敗")

        self.after(0, lambda: self._on_generate_done(success, total, failed, out_dir))

    def _on_generate_done(self, success: int, total: int, failed: list, out_dir: str):
        self.is_generating = False
        self.generate_btn.configure(state="normal", text="▶  一括生成")
        self.progress.set(1.0)

        msg = f"完了！ {success}/{total} 件の音声を生成しました。\n出力先: {out_dir}"
        if failed:
            msg += f"\n\n失敗した行:\n" + "\n".join(failed[:10])
            if len(failed) > 10:
                msg += f"\n...他 {len(failed) - 10} 件"
            self.progress_label.configure(text=f"完了（一部失敗）: {success}/{total}")
            messagebox.showwarning("生成完了（一部失敗）", msg)
        else:
            self.progress_label.configure(text=f"完了！ {success}/{total} 件")
            messagebox.showinfo("生成完了", msg)


if __name__ == "__main__":
    app = App()
    app.mainloop()