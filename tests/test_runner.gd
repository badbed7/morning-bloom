extends SceneTree
const Plant = preload("res://scripts/plant_state.gd")
const Store = preload("res://scripts/save_store.gd")
var failures := 0
var checks := 0
const T := 1800000000.0

func check(condition: bool, description: String) -> void:
	checks += 1
	if not condition:
		failures += 1
		push_error("FAIL: " + description)

func grown_state() -> RefCounted:
	var p := Plant.new(T)
	p.data.tutorial_used = true
	p.plant(T)
	return p

func _init() -> void:
	var p := Plant.new(T)
	check(p.plant(T), "first planting")
	check(not p.plant(T), "occupied pot cannot charge or consume another seed")
	p.advance(T + 59)
	check(not p.is_bloomed(), "tutorial not early")
	p.advance(T + 60)
	check(p.harvest(T + 60), "first harvest at 60 seconds")
	check(p.data.seeds == 1, "tutorial second seed awarded")
	check(not p.harvest(T + 60), "harvest cannot duplicate collection")
	check(p.plant(T + 60), "second planting")
	check(p.data.duration == Plant.NORMAL_DURATION, "tutorial cannot repeat")
	var g := grown_state()
	g.advance(T + 12 * 3600)
	check(is_equal_approx(g.ratio(), .5), "twelve hours yields half day growth")
	var before: float = g.data.growth
	g.care("water", T + 12 * 3600)
	g.care("water", T + 12 * 3600)
	check(g.data.growth == before and g.data.water_due == T + 2 * Plant.DAY, "early clicking cannot farm time")
	g.advance(T - 100)
	check(g.data.growth == before and g.data.last_update == T + 12 * 3600, "rollback does not lower timestamp or grant growth")
	g.advance(T + 12 * 3600 + 30)
	check(g.data.growth == before + 30, "no duplicate time after rollback")
	g.advance(T + Plant.DAY)
	check(g.is_bloomed(), "normal bloom at 24h")
	g.advance(T + 20 * Plant.DAY)
	check(g.is_bloomed() and g.health() == "개화 완료", "unharvested bloom never decays")
	var long_plant := grown_state()
	long_plant.data.duration = 10 * Plant.DAY
	long_plant.advance(T + 10 * Plant.DAY)
	check(long_plant.data.growth == 3 * Plant.DAY, "offline cap and grace boundary")
	check(long_plant.health().begins_with("시듦"), "overdue plant wilts")
	long_plant.care("water", T + 10 * Plant.DAY)
	check(long_plant.health().begins_with("시듦"), "all missing care must be restored")
	long_plant.care("mist", T + 10 * Plant.DAY)
	check(long_plant.health() == "건강하게 자라고 있어요", "free recovery preserves progress")
	long_plant.advance(T + 10 * Plant.DAY + 600)
	check(long_plant.data.growth == 3 * Plant.DAY + 600, "growth resumes after recovery")
	var vacation := grown_state()
	vacation.set_vacation(true, T)
	vacation.advance(T + 20 * Plant.DAY)
	check(vacation.data.growth == 0 and vacation.data.water_due == T + 22 * Plant.DAY, "vacation freezes growth and timers")
	vacation.set_vacation(false, T + 20 * Plant.DAY)
	vacation.advance(T + 20 * Plant.DAY + 90)
	check(vacation.data.growth == 90, "resume after vacation")
	var lump := grown_state()
	var stepped := grown_state()
	lump.data.duration = 10 * Plant.DAY
	stepped.data.duration = 10 * Plant.DAY
	lump.advance(T + 3 * Plant.DAY)
	for i in range(1, 73): stepped.advance(T + i * 3600)
	check(lump.data.growth == stepped.data.growth, "chunked and continuous time match within cap")
	check(p.sell_one() and p.data.coins == 170, "sell adds fixed revenue once")
	check(not p.sell_one() and p.data.coins == 170, "sold item cannot sell twice")
	_test_storage(p)
	print("%d checks, %d failures" % [checks, failures])
	quit(1 if failures > 0 else 0)

func _test_storage(p: RefCounted) -> void:
	var path := "user://test-%d.json" % Time.get_ticks_usec()
	var store := Store.new(path)
	check(store.save(p), "initial atomic save")
	var restored := Plant.new(T)
	check(store.load_into(restored), "load")
	check(restored.data == p.data, "JSON roundtrip preserves state and domain integer types")
	p.data.coins += 7
	check(store.save(p), "second save creates backup")
	var f := FileAccess.open(path, FileAccess.WRITE)
	f.store_string("{broken"); f.close()
	var recovering := Store.new(path)
	check(recovering.load_into(restored) and restored.data.coins == 170, "corrupt primary recovers previous valid backup")
	check(recovering.save(restored), "recovered state can save")
	check(Plant.valid(JSON.parse_string(FileAccess.get_file_as_string(path + ".bak"))), "recovery never copies corrupt primary over backup")
	var future: Dictionary = p.data.duplicate(true)
	future.schema = 99
	f = FileAccess.open(path, FileAccess.WRITE);f.store_string(JSON.stringify(future));f.close()
	var reader := Store.new(path)
	check(not reader.load_into(restored) and reader.read_only, "future schema cannot downgrade through backup")
	check(not reader.save(p), "future schema cannot overwrite")
	var invalid: Dictionary = p.data.duplicate(true)
	invalid.duration = 0
	check(not Plant.valid(invalid), "reject zero duration")
	invalid = p.data.duplicate(true);invalid.settings.opacity = -1
	check(not Plant.valid(invalid), "reject invalid opacity")
	invalid = p.data.duplicate(true);invalid.vacation = "false"
	check(not Plant.valid(invalid), "reject wrong boolean type")
	for suffix in ["", ".bak", ".tmp"]:
		if FileAccess.file_exists(path + suffix): DirAccess.remove_absolute(path + suffix)
