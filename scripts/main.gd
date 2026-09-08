extends Control
const Plant = preload("res://scripts/plant_state.gd")
const Store = preload("res://scripts/save_store.gd")
const Flower = preload("res://scripts/flower_view.gd")
const INK := Color("2e4e3f")
const MUTED := Color("758370")

var state: RefCounted
var store: RefCounted
var demo := false
var time_offset := 0.0
var tick := 0.0
var save_tick := 0.0
var notice_until := 0.0
var dragging := false
var drag_mouse := Vector2i.ZERO
var drag_window := Vector2i.ZERO
var closing := false
var save_path_override := "" # Injected before _ready by integration tests only.

var content: PanelContainer
var flower: Control
var stage_label: Label
var health_label: Label
var progress_label: Label
var progress: ProgressBar
var primary: Button
var water: Button
var mist: Button
var message: Label
var funds: Label
var settings_panel: PanelContainer
var collection_panel: PanelContainer
var collection_label: Label
var sell_button: Button
var opacity_slider: HSlider
var top_check: CheckBox
var vacation_check: CheckBox

func now() -> float:
	return Time.get_unix_time_from_system() + time_offset

func _ready() -> void:
	demo = "--demo" in OS.get_cmdline_user_args()
	state = Plant.new(now())
	var save_path := "user://demo-garden.json" if demo else "user://garden.json"
	store = Store.new(save_path_override if not save_path_override.is_empty() else save_path)
	store.load_into(state)
	# A demo clock resumes from its own watermark, never from the real garden.
	if demo:
		time_offset = maxf(0.0, float(state.data.last_update) - Time.get_unix_time_from_system())
	var offline: float = state.advance(now())
	Engine.max_fps = 30
	get_window().transparent = true
	get_window().transparent_bg = true
	get_window().min_size = Vector2i(320, 320)
	get_tree().auto_accept_quit = false
	get_window().close_requested.connect(_close)
	_make_theme()
	_build_ui()
	_position_window()
	_apply_settings()
	_refresh()
	if not store.error_message.is_empty():
		_notify(store.error_message, 15.0)
	elif offline >= 60:
		_notify("다시 오셨네요. 꽃이 %s만큼 자랐어요." % _duration(offline), 8)
	else:
		_notify("작은 화분에서 오늘을 시작해요.", 5)
	_save()

func _make_theme() -> void:
	theme = Theme.new()
	theme.default_font = load("res://assets/fonts/NotoSansKR-Subset.otf")
	theme.default_font_size = 14
	theme.set_color("font_color", "Label", INK)
	for type in ["Button", "CheckBox"]:
		theme.set_color("font_color", type, INK)
		theme.set_color("font_hover_color", type, INK)
		theme.set_color("font_pressed_color", type, INK)
		theme.set_color("font_disabled_color", type, Color("9baba0"))
	for key in ["normal", "hover", "pressed", "disabled", "focus"]:
		var b := _box(Color("e9edde") if key != "hover" else Color("dce5cf"), 9)
		b.content_margin_left = 10
		b.content_margin_right = 10
		b.content_margin_top = 4
		b.content_margin_bottom = 4
		if key == "focus":
			b.bg_color = Color(0, 0, 0, 0)
			b.border_color = Color("769777")
			b.set_border_width_all(2)
		theme.set_stylebox(key, "Button", b)

func _box(color: Color, radius: int = 16) -> StyleBoxFlat:
	var b := StyleBoxFlat.new()
	b.bg_color = color
	b.set_corner_radius_all(radius)
	return b

func _label(text: String, font_size: int = 14, color: Color = INK) -> Label:
	var l := Label.new()
	l.text = text
	l.add_theme_font_size_override("font_size", font_size)
	l.add_theme_color_override("font_color", color)
	return l

func _button(text: String, action: Callable) -> Button:
	var b := Button.new()
	b.text = text
	b.custom_minimum_size.y = 32
	b.pressed.connect(action)
	return b

func _build_ui() -> void:
	content = PanelContainer.new()
	content.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	content.add_theme_stylebox_override("panel", _box(Color("f8f6ed"), 18))
	add_child(content)
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 12)
	content.add_child(margin)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 3)
	margin.add_child(column)
	var bar := HBoxContainer.new()
	column.add_child(bar)
	var title := _label("아침 한 송이" + (" · 데모" if demo else ""), 16)
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	title.mouse_filter = Control.MOUSE_FILTER_STOP
	title.mouse_default_cursor_shape = Control.CURSOR_MOVE
	title.tooltip_text = "이곳을 드래그하면 창을 옮길 수 있어요."
	title.gui_input.connect(_drag_input)
	bar.add_child(title)
	bar.add_child(_button("설정", func(): settings_panel.show()))
	var exit_button := _button("×", _close)
	exit_button.tooltip_text = "저장하고 종료"
	bar.add_child(exit_button)
	var sub := _label("당신의 하루 곁에, 작은 정원", 12, MUTED)
	column.add_child(sub)
	flower = Flower.new()
	flower.custom_minimum_size.y = 90
	flower.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(flower)
	var stage_row := HBoxContainer.new()
	column.add_child(stage_row)
	stage_label = _label("빈 화분", 18)
	stage_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	stage_row.add_child(stage_label)
	progress_label = _label("", 12, MUTED)
	stage_row.add_child(progress_label)
	health_label = _label("", 12, MUTED)
	column.add_child(health_label)
	progress = ProgressBar.new()
	progress.custom_minimum_size.y = 5
	progress.show_percentage = false
	progress.add_theme_stylebox_override("background", _box(Color("e3e7da"), 3))
	progress.add_theme_stylebox_override("fill", _box(Color("8fa77b"), 3))
	column.add_child(progress)
	var actions := HBoxContainer.new()
	column.add_child(actions)
	water = _button("물주기", func(): _care("water"))
	mist = _button("분무", func(): _care("mist"))
	primary = _button("씨앗 심기", _primary_action)
	primary.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	actions.add_child(water)
	actions.add_child(mist)
	actions.add_child(primary)
	message = _label("", 12, MUTED)
	message.custom_minimum_size.y = 20
	message.text_overrun_behavior = TextServer.OVERRUN_TRIM_ELLIPSIS
	column.add_child(message)
	var bottom := HBoxContainer.new()
	column.add_child(bottom)
	funds = _label("", 12, MUTED)
	funds.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	bottom.add_child(funds)
	bottom.add_child(_button("보관함", _show_collection))
	if demo:
		bottom.add_child(_button("+6시간", _fast_forward))
	settings_panel = _overlay("설정")
	var settings := settings_panel.get_meta("column") as VBoxContainer
	settings.add_child(_label("창 불투명도", 14))
	opacity_slider = HSlider.new()
	opacity_slider.min_value = 0.1
	opacity_slider.max_value = 1.0
	opacity_slider.step = 0.1
	opacity_slider.custom_minimum_size.y = 32
	opacity_slider.value = float(state.data.settings.opacity)
	opacity_slider.value_changed.connect(func(value: float):
		state.data.settings.opacity = value
		_apply_settings()
		_save())
	settings.add_child(opacity_slider)
	top_check = CheckBox.new()
	top_check.text = "항상 위에 표시"
	top_check.button_pressed = state.data.settings.topmost
	top_check.toggled.connect(func(enabled: bool):
		state.data.settings.topmost = enabled
		_apply_settings()
		_save())
	settings.add_child(top_check)
	vacation_check = CheckBox.new()
	vacation_check.text = "휴가 모드 · 성장과 돌봄 일시 정지"
	vacation_check.button_pressed = state.data.vacation
	vacation_check.disabled = store.read_only
	vacation_check.toggled.connect(func(enabled: bool):
		state.set_vacation(enabled, now())
		_save()
		_refresh())
	settings.add_child(vacation_check)
	settings.add_child(_button("창 위치와 불투명도 복구", _reset_window))
	settings.add_child(_button("저장 폴더 열기", func(): OS.shell_open(ProjectSettings.globalize_path("user://"))))
	var note := _label("첫 꽃은 60초, 다음 꽃은 24시간 자라요.\n종료해도 최대 72시간 성장을 계산해요.", 12, MUTED)
	note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	settings.add_child(note)
	settings.add_child(_button("닫기", func(): settings_panel.hide()))
	collection_panel = _overlay("테라리움 보관함")
	var bag := collection_panel.get_meta("column") as VBoxContainer
	collection_label = _label("", 16)
	collection_label.custom_minimum_size.y = 65
	bag.add_child(collection_label)
	bag.add_child(_label("보관한 꽃은 시들지 않아요.\n판매한 꽃은 보관함에서 사라져요.", 13, MUTED))
	sell_button = _button("데이지 1개 판매 · +50G", _sell)
	bag.add_child(sell_button)
	bag.add_child(_button("돌아가기", func(): collection_panel.hide()))

func _overlay(title: String) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	panel.offset_left = 8
	panel.offset_top = 8
	panel.offset_right = -8
	panel.offset_bottom = -8
	panel.add_theme_stylebox_override("panel", _box(Color("f8f6ed")))
	add_child(panel)
	var margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		margin.add_theme_constant_override("margin_" + side, 18)
	panel.add_child(margin)
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	margin.add_child(scroll)
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 10)
	scroll.add_child(column)
	panel.set_meta("column", column)
	column.add_child(_label(title, 20))
	panel.hide()
	return panel

func _position_window() -> void:
	if DisplayServer.get_name() == "headless": return
	var usable := DisplayServer.screen_get_usable_rect()
	var edge := clampi(int(usable.size.x * .2), 320, 520)
	get_window().size = Vector2i(edge, edge)
	var desired := Vector2i(int(state.data.settings.x), int(state.data.settings.y))
	var fits := false
	for i in range(DisplayServer.get_screen_count()):
		if DisplayServer.screen_get_usable_rect(i).encloses(Rect2i(desired, get_window().size)):
			fits = true
	if not fits:
		desired = usable.end - get_window().size - Vector2i(16, 16)
	get_window().position = desired

func _apply_settings() -> void:
	content.modulate.a = float(state.data.settings.opacity)
	if DisplayServer.get_name() != "headless":
		get_window().always_on_top = state.data.settings.topmost

func _reset_window() -> void:
	state.data.settings.x = -99999
	state.data.settings.y = -99999
	opacity_slider.value = 1.0
	_position_window()
	_save()

func _drag_input(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		dragging = event.pressed
		drag_mouse = DisplayServer.mouse_get_position()
		drag_window = get_window().position
		if not dragging: _save()

func _input(event: InputEvent) -> void:
	if event is InputEventMouseButton and not event.pressed and dragging:
		dragging = false
		_save()
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		settings_panel.hide()
		collection_panel.hide()

func _process(delta: float) -> void:
	if state == null: return
	if dragging:
		get_window().position = drag_window + DisplayServer.mouse_get_position() - drag_mouse
	tick += delta
	save_tick += delta
	if tick >= 1.0:
		tick = 0.0
		state.advance(now())
		_refresh()
	if save_tick >= 30.0:
		save_tick = 0.0
		_save()

func _refresh() -> void:
	flower.planted = state.data.planted
	flower.growth_stage = state.stage()
	flower.wilted = state.health().begins_with("시듦")
	stage_label.text = Plant.STAGES[state.stage()] if state.data.planted else "무엇을 심어볼까요?"
	health_label.text = state.health()
	progress.value = state.ratio() * 100
	var remaining := maxf(0, float(state.data.duration) - float(state.data.growth))
	progress_label.text = _duration(remaining) if state.data.planted and not state.is_bloomed() else ""
	primary.text = "테라리움 보관" if state.is_bloomed() else ("자라는 중" if state.data.planted else ("씨앗 심기" if int(state.data.seeds) > 0 else "심기 · 20G"))
	primary.disabled = store.read_only or state.data.vacation or (state.data.planted and not state.is_bloomed()) or (not state.data.planted and int(state.data.seeds) == 0 and int(state.data.coins) < 20)
	water.disabled = store.read_only or not state.data.planted or state.is_bloomed() or state.data.vacation
	mist.disabled = water.disabled
	water.tooltip_text = "다음 물주기: " + _duration(maxf(0, float(state.data.water_due) - float(state.data.last_update)))
	mist.tooltip_text = "다음 분무: " + _duration(maxf(0, float(state.data.mist_due) - float(state.data.last_update)))
	funds.text = "%dG  ·  씨앗 %d개" % [state.data.coins, state.data.seeds]
	if collection_label != null:
		collection_label.text = "데이지 %d송이가 쉬고 있어요." % state.data.collection.size()
		sell_button.disabled = store.read_only or state.data.collection.is_empty()
	if Time.get_ticks_msec() / 1000.0 > notice_until:
		message.text = "첫 꽃은 60초 만에 피어요." if state.data.planted and float(state.data.duration) == Plant.TUTORIAL_DURATION else "오늘도 천천히, 나만의 속도로."

func _duration(seconds: float) -> String:
	if seconds < 60: return "%d초" % ceili(seconds)
	if seconds < 3600: return "%d분" % ceili(seconds / 60)
	return "%d시간 %d분" % [int(seconds / 3600), int(fmod(seconds, 3600) / 60)]

func _notify(text: String, seconds: float = 4.0) -> void:
	message.text = text
	message.tooltip_text = text
	notice_until = Time.get_ticks_msec() / 1000.0 + seconds

func _primary_action() -> void:
	if store.read_only: return
	if state.is_bloomed():
		if state.harvest(now()): _notify("데이지를 보관했어요. 새 꽃을 심어볼까요?")
	elif state.plant(now()):
		_notify("씨앗을 심었어요. 첫 변화를 기다려 보세요.")
	_save()
	_refresh()

func _care(kind: String) -> void:
	if store.read_only: return
	if state.care(kind, now()):
		flower.splash = 1.0
		_notify("촉촉하게 돌봐줬어요. 필요한 시점에만 시간이 갱신돼요.")
	_save()
	_refresh()

func _show_collection() -> void:
	_refresh()
	collection_panel.show()

func _sell() -> void:
	if store.read_only: return
	if state.sell_one():
		_save()
		_refresh()

func _fast_forward() -> void:
	if not demo or store.read_only: return
	time_offset += 6 * 3600
	state.advance(now())
	_save()
	_refresh()
	_notify("데모 시간만 6시간 진행했어요.")

func _save() -> bool:
	if store.read_only: return false
	state.advance(now())
	if DisplayServer.get_name() != "headless":
		state.data.settings.x = get_window().position.x
		state.data.settings.y = get_window().position.y
	var ok: bool = store.save(state)
	if not ok and message != null:
		_notify(store.error_message, 30)
	return ok

func _close() -> void:
	if closing: return
	# If a normal save fails, keep the app open so the user can recover it.
	if not store.read_only and not _save(): return
	closing = true
	get_tree().quit()
