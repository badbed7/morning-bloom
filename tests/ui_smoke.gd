extends SceneTree
## Run with -- --demo. Optional --capture writes local QA images only.
var failures := 0

func _init() -> void:
	call_deferred("run")

func verify(condition: bool, text: String) -> void:
	if not condition:
		failures += 1
		push_error(text)

func run() -> void:
	var app = load("res://scenes/main.tscn").instantiate()
	var test_path := "user://ui-test-%d.json" % Time.get_ticks_usec()
	app.save_path_override = test_path
	root.add_child(app)
	await process_frame
	app.state = load("res://scripts/plant_state.gd").new(app.now())
	app._refresh()
	root.size = Vector2i(420, 420)
	await process_frame
	await process_frame
	verify(app.content.get_combined_minimum_size().y <= 420, "Home must fit 420px")
	app._primary_action()
	verify(app.state.data.planted, "UI planting")
	app._care("water")
	app._fast_forward()
	verify(app.state.is_bloomed(), "Demo button grows tutorial flower")
	await process_frame
	await process_frame
	if "--capture" in OS.get_cmdline_user_args() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("/tmp/morning-bloom-home.png")
	app.settings_panel.show()
	await process_frame
	await process_frame
	verify(app.settings_panel.get_combined_minimum_size().y <= 404, "Settings must fit or scroll")
	if "--capture" in OS.get_cmdline_user_args() and DisplayServer.get_name() != "headless":
		await RenderingServer.frame_post_draw
		root.get_texture().get_image().save_png("/tmp/morning-bloom-settings.png")
	app.settings_panel.hide()
	app._primary_action()
	verify(app.state.data.collection.size() == 1 and not app.state.data.planted, "UI harvest")
	app._show_collection()
	app._sell()
	verify(app.state.data.coins == 170 and app.state.data.collection.is_empty(), "UI sale")
	verify(app._save(), "UI save")
	app.set_process(false)
	for suffix in ["", ".bak", ".tmp"]:
		if FileAccess.file_exists(test_path + suffix):
			DirAccess.remove_absolute(test_path + suffix)
	print("UI smoke: %d failures" % failures)
	quit(1 if failures > 0 else 0)
