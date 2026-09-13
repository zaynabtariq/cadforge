import marimo

__generated_with = "0.24.2"
app = marimo.App(width="medium", app_title="CADForge Design Studio")


@app.cell
def _():
    import marimo as mo
    from pathlib import Path
    import uuid
    from cadforge.planner import parse_request
    from cadforge.schema import DesignSpec
    from cadforge.enhanced_geometry import build_design, export_design, validate_enhanced_design as validate_design
    return DesignSpec, Path, build_design, export_design, mo, parse_request, uuid, validate_design


@app.cell
def _(mo):
    mo.md("""
    # CADForge Design Studio

    Describe glasses, an enclosure, a bracket, or a clip. Edit the dimensions,
    then select **Build design** to generate an editable CAD model and measured
    geometry checks. Every dimension is in millimeters.

    The four sliders override those dimensions in your request. Other dimensions
    can be written as `board_width=30 mm` or `camera_diameter=8 mm`.
    """)
    return


@app.cell
def _(mo):
    design_form = mo.md("""
    **Your design**

    {request}

    {wall}

    {clearance}

    {lens_width}

    {lens_height}
    """).batch(
        request=mo.ui.text_area(
            value="Glasses housing a camera and Raspberry Pi Zero 2 W, camera_diameter=8 mm",
            rows=3, full_width=True, max_length=3000,
        ),
        wall=mo.ui.slider(0.5, 6.0, step=0.1, value=2.0, label="Wall", show_value=True),
        clearance=mo.ui.slider(0.1, 3.0, step=0.1, value=0.6, label="Clearance", show_value=True),
        lens_width=mo.ui.slider(25.0, 75.0, step=1.0, value=48.0, label="Lens width", show_value=True),
        lens_height=mo.ui.slider(20.0, 60.0, step=1.0, value=34.0, label="Lens height", show_value=True),
    ).form(submit_button_label="Build design", show_clear_button=False)
    design_form
    return (design_form,)


@app.cell
def _(DesignSpec, Path, build_design, design_form, export_design, mo, parse_request, uuid, validate_design):
    mo.stop(design_form.value is None, mo.md("Submit the form to create your first design."))
    _submitted = design_form.value
    studio_error = None
    studio_paths = {}
    studio_report = None
    studio_spec = None
    try:
        _parsed = parse_request(_submitted["request"])
        _parameters = dict(_parsed.parameters)
        _parameters.update({key: float(_submitted[key]) for key in ("wall", "clearance", "lens_width", "lens_height")})
        studio_spec = DesignSpec(family=_parsed.family, name="studio-design", parameters=_parameters)
        _built = build_design(studio_spec)
        studio_report = validate_design(_built)
        _destination = Path(__file__).resolve().parents[1] / "artifacts" / "studio" / uuid.uuid4().hex[:12]
        studio_paths = export_design(_built, _destination)
        (_destination / "validation.json").write_text(studio_report.model_dump_json(indent=2) + "\n")
    except Exception as _error:
        studio_error = f"{type(_error).__name__}: {_error}"
    return studio_error, studio_paths, studio_report, studio_spec


@app.cell
def _(Path, mo, studio_error, studio_paths, studio_report, studio_spec):
    mo.stop(studio_error is not None, mo.callout(studio_error or "", kind="danger"))
    mo.stop(not studio_paths)
    _status = "Geometry checks passed" if studio_report.passed else "Geometry checks failed — revise dimensions"
    _preview = mo.Html(Path(studio_paths["svg"]).read_text())
    _downloads = [mo.download(Path(studio_paths[_kind]).read_bytes(),
                              filename=Path(studio_paths[_kind]).name,
                              label=_label)
                  for _kind, _label in [("json", "Parameters JSON"), ("step", "STEP assembly"),
                                        ("stl", "STL mesh"), ("python", "Editable Python")]]
    mo.vstack([
        mo.md(f"## {_status}"),
        _preview,
        mo.hstack(_downloads, justify="start", wrap=True),
        mo.ui.table([check.model_dump() for check in studio_report.checks], selection=None),
        mo.accordion({"Editable specification": mo.json(studio_spec.model_dump()),
                      "Measured geometry": mo.json(studio_report.measurements)}),
        mo.callout(mo.md("**Engineering limits**\n\n" + "\n\n".join(studio_report.limitations)), kind="warn"),
    ])
    return


if __name__ == "__main__":
    app.run()
