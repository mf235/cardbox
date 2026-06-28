CardBox v1.0.0
================

CardBoxは、タイトル・タグ・本文・メディアファイルをカード単位で管理するローカルGUIツールです。
AIプロンプト管理から、メモ、資料、メディア管理まで、ワークスペースを切り替えて使えます。

起動方法
--------
Python版:
  python cardbox.py

必要ライブラリ:
  pip install PySide6 opencv-python

保存データ
--------
同じフォルダに cardbox.db と assets/ を作成します。

AI Prompt Organizer からの移行
-----------------------------
初回起動時、同じフォルダに cardbox.db がなく、prompt_organizer.db がある場合は、
prompt_organizer.db を cardbox.db にコピーしてからCardBox用スキーマへ移行します。

重要:
  prompt_organizer.db は直接変更しません。
  assets/ は分けずにそのまま使います。
  アプリ管理下メディアのDB保存は assets/... の相対パスを基本にします。


対応ファイル形式
--------------
基本的にすべてのファイルをメディアとして登録できます。
未分類のファイルはカードに添付し、OSの関連付けで開きます。

画像として扱う形式:
  .bmp .gif .ico .jpeg .jpg .png .svg .tga .tif .tiff .webp

動画として扱う形式:
  .avi .mkv .mov .mp4 .webm

その他の主な分類:
  音声: .flac .m4a .mp3 .ogg .wav
  圧縮: .7z .gz .rar .tar .zip
  文書: .doc .docx .pdf .ppt .pptx .xls .xlsx
  テキスト: .css .csv .html .js .json .md .py .txt .xml .yaml .yml
  コード: .c .cpp .cs .css .go .h .html .java .js .py .rs .ts

補足:
  上記以外の拡張子も登録できます。
  ただし、サムネイルや専用プレビューは形式により作成できない場合があります。

主な機能
--------
- カード形式で情報を管理
- ワークスペース切り替え
- ワークスペースごとのタグ管理
- ワークスペースごとの表示ラベル変更
- ワークスペースごとのカードリストサムネ表示ON/OFF
- カード一覧の並び替え（更新日時 / タイトル）
- ワークスペース削除（DBバックアップ、確認ダイアログ、メディアのゴミ箱移動）
- 画像・動画・各種ファイルをメディアとしてカードに登録
- メディアのD&D追加
- クリップボード画像のメディア登録
- 画像ビュアー表示
- メディアフォルダを開く
- メディアをエクスプローラーで表示
- 設定・ウィンドウ状態の保存

注意
----
CardBox v1.0.0 は最初の正式リリース候補です。
AI Prompt Organizer から移行する場合も、元の prompt_organizer.db は直接変更しません。
