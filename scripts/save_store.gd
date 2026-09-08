extends RefCounted
const Plant = preload("res://scripts/plant_state.gd")
var path: String
var error_message := ""
var read_only := false

func _init(file_path: String = "user://garden.json") -> void:
	path = file_path

func _read(file_path: String) -> Variant:
	if not FileAccess.file_exists(file_path): return null
	var f := FileAccess.open(file_path, FileAccess.READ)
	if f == null: return null
	var parser := JSON.new()
	var status := parser.parse(f.get_as_text())
	f.close()
	return parser.data if status == OK else null

func load_into(state: RefCounted) -> bool:
	var primary: Variant = _read(path)
	# A newer schema belongs to a newer application: don't replace it with an older backup.
	if primary is Dictionary and primary.get("schema", 0) > 1:
		read_only = true
		error_message = "더 최신 버전의 저장 파일입니다. 이 버전에서는 변경하지 않아요."
		return false
	if Plant.valid(primary):
		_restore(state, primary)
		return true
	var backup: Variant = _read(path + ".bak")
	if Plant.valid(backup):
		_restore(state, backup)
		error_message = "이전 정상 저장 기록으로 복구했어요."
		return true
	if FileAccess.file_exists(path) or FileAccess.file_exists(path + ".bak"):
		read_only = true
		error_message = "저장 파일을 읽지 못했어요. 원본을 보존했으니 저장 폴더를 확인해 주세요."
	return false

func _restore(state: RefCounted, saved: Dictionary) -> void:
	# JSON decodes every number as float. Restore the domain's integer fields.
	state.data = saved
	for key in ["schema", "coins", "seeds"]:
		state.data[key] = int(state.data[key])
	for key in ["x", "y"]:
		state.data.settings[key] = int(state.data.settings[key])

func save(state: RefCounted) -> bool:
	if read_only: return false
	if not Plant.valid(state.data):
		error_message = "저장할 상태를 확인하지 못했어요."
		return false
	var tmp := path + ".tmp"
	var f := FileAccess.open(tmp, FileAccess.WRITE)
	if f == null:
		error_message = "저장 파일을 만들 수 없어요. 저장 폴더 권한을 확인해 주세요."
		return false
	f.store_string(JSON.stringify(state.data, "", true, true))
	f.flush()
	var write_error := f.get_error()
	f.close()
	if write_error != OK or not Plant.valid(_read(tmp)):
		error_message = "저장을 끝내지 못했어요. 기존 기록을 유지합니다."
		return false
	if Plant.valid(_read(path)):
		var copied := DirAccess.copy_absolute(path, path + ".bak")
		if copied != OK:
			error_message = "백업 파일을 만들지 못해 저장을 중단했어요."
			return false
	var result := DirAccess.rename_absolute(tmp, path)
	if result != OK:
		error_message = "저장 파일 교체에 실패했어요. 기존 기록을 유지합니다."
		return false
	return true
