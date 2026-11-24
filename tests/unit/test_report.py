"""Report generation test."""

from sales_trainer.report import Report, TurnInfo, generate_report


def test_turn_info_creation() -> None:
    """TurnInfo can be created with required fields."""
    t = TurnInfo(
        user_text="Hola, soy Marta",
        words=["hola", "soy", "Marta"],
        audio_ms=500,
        temperature=50,
        cause="inicio de conversación",
    )
    assert t.user_text == "Hola, soy Marta"
    assert t.words == ["hola", "soy", "Marta"]
    assert t.audio_ms == 500
    assert t.temperature == 50
    assert t.cause == "inicio de conversación"


def test_report_creation() -> None:
    """Report can be created with required fields."""
    r = Report(
        session_token="sess-12345",
        character_level=1,
        character_name="Marta",
        max_turns=10,
    )
    assert r.session_token == "sess-12345"
    assert r.character_level == 1
    assert r.character_name == "Marta"
    assert r.max_turns == 10
    assert r.turns == []
    assert r.final_temperature == 50
    assert r.final_cause == ""
    assert r.won is False


def test_generate_report_has_sections() -> None:
    """generate_report produces a string with the expected sections."""
    r = Report(
        session_token="sess-abc",
        character_level=2,
        character_name="Javier",
        max_turns=10,
    )
    r.turns.append(
        TurnInfo(
            user_text="Hola, quiero información",
            words=["hola", "quiero", "información"],
            audio_ms=450,
            temperature=55,
            cause="score 6 en proposition",
            judge_scores={"value proposition": 6, "quantified time savings": 5},
        )
    )
    r.final_temperature = 58
    r.final_cause = "score 6 en proposition"
    r.won = False

    report = generate_report(r)
    assert report != ""
    assert "REPORTE DE SESIÓN SALES TRAINER" in report
    assert "Token de sesión: sess-abc" in report
    assert "Nivel 2 - Javier" in report
    assert "HISTORIAL DE TURNOS" in report
    assert "Temperatura final: 58°C" in report
    assert "Causa final: score 6 en proposition" in report
    assert "DERROTA" in report  # check result section exists


def test_generate_report_with_win() -> None:
    """generate_report with win flag."""
    r = Report(
        session_token="sess-win",
        character_level=1,
        character_name="Marta",
        max_turns=10,
    )
    r.won = True
    r.final_temperature = 80
    r.final_cause = "Umbral alcanzado 2 veces consecutivas"

    report = generate_report(r)
    assert "VICTORIA" in report
    assert "Temperatura final: 80°C" in report
