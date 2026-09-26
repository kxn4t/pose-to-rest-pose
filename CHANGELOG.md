# Changelog / 更新履歴

🇬🇧 **English** | 🇯🇵 **日本語**

All notable changes to this project will be documented in this file.
このプロジェクトの注目すべき変更はすべてこのファイルに記録されます。

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
フォーマットは [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) に基づいており、
このプロジェクトは [Semantic Versioning](https://semver.org/spec/v2.0.0.html) に準拠しています。

## [Unreleased]

### Added

- Show a warning when a Mirror modifier is placed before the Armature modifier, since the result is correct only for symmetric poses

### Changed

- Remove the claim that shape key custom properties are preserved, along with the handling code that had no effect (shape keys cannot hold custom properties)
- Clarify the modifier order section in README: explain the actual reason deformation modifiers before the Armature modifier are rejected, and document the Mirror modifier limitation

### Fixed

- Fix deformation modifiers placed after the Armature modifier (Displace, Shrinkwrap, Simple Deform, etc.) being baked into shape keys and applied twice

### 追加

- アーマチュアモディファイアより前にミラーモディファイアがある場合に警告を表示するようにしました（左右対称のポーズでのみ正しい結果になるため）。

### 変更

- シェイプキーのカスタムプロパティを保持するという記載と、実際には効果のなかった処理を削除しました（シェイプキーはカスタムプロパティを持てないため）。
- README のモディファイア順序の説明を修正しました。アーマチュアモディファイアより前の変形モディファイアを拒否する実際の理由を記載し、ミラーモディファイアの制限事項を追記しています。

### 修正

- アーマチュアモディファイアより後ろにある変形モディファイア（ディスプレイス、シュリンクラップ、シンプル変形など）の効果がシェイプキーに焼き込まれ、二重にかかる問題を修正しました。

## [0.4.0] - 2026-04-01

### Changed

- Migrate to Blender Extension format (Blender 4.2+ only)
- Add `blender_manifest.toml` as the single source of version and metadata
- Remove legacy `bl_info` dictionary
- v0.3.0 is the final version supporting Blender 3.6–4.1

### 変更

- Blender Extension 形式に移行しました（Blender 4.2 以降専用）。
- `blender_manifest.toml` をバージョン・メタデータの単一情報源とし、従来の `bl_info` を削除しました。
- Blender 3.6〜4.1 をお使いの方は v0.3.0 をご利用ください。

## [0.3.0] - 2026-03-26

### Added

- Reject objects with shared (linked) mesh data before processing, with a clear error message prompting the user to make them single-user first

### Improved

- Process all meshes referencing the target armature across all scenes, since `pose.armature_apply()` modifies the armature data block itself
- Improve driver restoration accuracy with correct shape key data block reference remapping
- Preserve Mesh and Key data block names after processing (previously could change to `.001` suffixed names)
- Preserve Basis shape key name after processing
- Add ViewLayerScope for stable operation with hidden collections and objects outside current view layer
- Improve error safety with two-phase execution model (non-destructive preparation before irreversible changes)

### Changed

- Update README to document shared mesh data limitation, non-preserved data, and other improvements

### 追加

- 共有（リンク）メッシュデータを持つオブジェクトを処理前に検出し、シングルユーザー化を促すエラーメッセージを表示

### 改善

- `pose.armature_apply()` はアーマチュアのデータブロック自体を変更するため、全シーンを横断して対象アーマチュアを参照するすべてのメッシュを処理するように改善
- ドライバーの復元精度を向上（シェイプキーデータへの参照をより正確にリマップするように改善）
- 処理後にメッシュおよび Key データブロックの名前が維持されるように改善（従来は `.001` 等の接尾辞が付くことがあった）
- 処理後に Basis シェイプキーの名前が維持されるように改善
- 非表示コレクションやビューレイヤー外のオブジェクトを処理する際の安定性を向上（ViewLayerScope の導入）
- 処理途中でエラーが発生した場合の安全性を強化（破壊的操作の前段階で問題を検出した場合、安全にキャンセル可能に）

### 変更

- README に共有メッシュデータの制限事項、保持されないデータ、その他の改善について追記

## [0.2.1] - 2025-06-26

### Fixed

- Fix some missing Japanese translations in menu items

### 修正

- メニュー項目の一部で日本語翻訳が反映されない問題を修正

## [0.2.0] - 2025-06-26

### Added

- Add Japanese language support

### 追加

- 日本語対応を追加

## [0.1.1] - 2025-06-08

### Fixed

- Fix UTF-8 related errors
- Fix `mode_set` error caused by an invalid object remaining active after deleting temporary objects

### 修正

- UTF-8 関連のエラーを修正
- 一時オブジェクト削除後に無効なオブジェクトがアクティブのまま残り `mode_set` エラーが発生する問題を修正

## [0.1.0] - 2025-06-05

Initial release.
初版リリース。

### Added

- Apply current pose as rest pose while preserving shape keys, drivers, and modifier settings
- Automatic detection of all meshes with Armature modifiers targeting the selected armature
- Shape key property preservation (value, slider range, mute, interpolation, relative key, vertex group, custom properties)
- Driver backup and restoration
- Armature modifier settings and stack position restoration
- Modifier order validation with warnings for potentially problematic configurations

### 追加

- シェイプキー・ドライバー・モディファイア設定を保持したまま現在のポーズをレストポーズとして適用
- 選択したアーマチュアをターゲットとするアーマチュアモディファイアを持つすべてのメッシュを自動検出
- シェイプキープロパティの保持（値、スライダー範囲、ミュート、補間、相対キー、頂点グループ、カスタムプロパティ）
- ドライバーのバックアップと復元
- アーマチュアモディファイアの設定とスタック位置の復元
- モディファイア順序のバリデーションと潜在的な問題の警告
