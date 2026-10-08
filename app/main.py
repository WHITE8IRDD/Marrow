import sys
from pathlib import Path

# Make `import marrow` work even if the package isn't pip-installed.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st  # noqa: E402

from marrow.pipeline import run_pipeline  # noqa: E402

st.set_page_config(page_title="Marrow", page_icon="🎬", layout="wide")
st.title("🎬 Marrow")
st.caption("Pull the best moments out of long videos as captioned Shorts and Reels. Runs locally.")

source = st.text_input("YouTube URL or local file path")

c1, c2, c3 = st.columns(3)
num_clips = c1.slider("Number of clips", 1, 10, 5)
duration = c2.slider("Target length (seconds)", 15, 120, 45)
platform = c3.selectbox("Output format", ["shorts", "reels", "both"], index=2)

with st.expander("Advanced"):
    layout = st.radio("Layout", ["crop", "blur_fit"], horizontal=True,
                      help="crop = center crop; blur_fit = full frame over a blurred background")
    use_llm = st.checkbox("Use Ollama LLM scoring", value=True)

if st.button("Generate clips", type="primary"):
    if not source.strip():
        st.warning("Enter a YouTube URL or a file path.")
    else:
        bar = st.progress(0.0)
        status = st.empty()

        def on_progress(stage, frac):
            bar.progress(min(1.0, frac))
            status.write(stage)

        try:
            st.session_state["results"] = run_pipeline(
                source.strip(), clip_count=num_clips, clip_duration=duration,
                platform=platform, layout=layout, use_llm=use_llm, progress=on_progress,
            )
            status.write("Done")
        except Exception as e:  # show the real error instead of failing silently
            st.session_state.pop("results", None)
            st.error(f"{type(e).__name__}: {e}")

for r in st.session_state.get("results", []):
    st.subheader(f"#{r['rank']}  {r['title']}")
    st.caption(f"{r['duration']:.0f}s · score {r['score']:.2f} · {r['reason']}")
    if r["hashtags"]:
        st.write(" ".join(f"#{t}" for t in r["hashtags"]))
    cols = st.columns(len(r["files"]))
    for col, (plat, path) in zip(cols, r["files"].items()):
        col.video(path)
        col.download_button(f"Download {plat}", Path(path).read_bytes(),
                            file_name=Path(path).name, key=f"{r['rank']}-{plat}")
