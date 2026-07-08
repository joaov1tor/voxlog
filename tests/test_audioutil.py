from pathlib import Path
from voxlog.audioutil import combine_segments


def test_combine_segments_monta_concat_ffmpeg(tmp_path):
    s1 = tmp_path / "a_1.m4a"; s1.write_bytes(b"1")
    s2 = tmp_path / "a_2.m4a"; s2.write_bytes(b"2")
    dest = tmp_path / "full.m4a"
    cmds = []
    def runner(cmd):
        cmds.append(cmd)
        dest.write_bytes(b"FULL")   # simula o ffmpeg gerando o arquivo
    out = combine_segments([s1, s2], dest, runner=runner)
    assert out == dest and dest.exists()
    flat = " ".join(cmds[0])
    assert "ffmpeg" in flat and "concat" in flat and str(dest) in flat


def test_combine_segments_um_segmento_copia(tmp_path):
    s1 = tmp_path / "a_1.m4a"; s1.write_bytes(b"SO")
    dest = tmp_path / "full.m4a"
    out = combine_segments([s1], dest)   # sem runner: 1 seg = cópia, não chama ffmpeg
    assert out == dest and dest.read_bytes() == b"SO"
