/**
 * Washing Machine Animated Card - Predictor Extension
 *
 * Optional companion extension for sionetta/wm_animated_ha_card.
 * This file does not replace or bundle the original card.
 *
 * Prototype version: 0.1.0
 */
(() => {
    "use strict";

    const EXTENSION_VERSION = "0.1.0";
    const CARD_TAG = "washing-machine-card";
    const PATCH_FLAG = Symbol.for("alp.washingMachineCardPredictorExtension");

    const STRINGS = {
        en: {
            title: "PREDICTION",
            start: "START",
            expected: "EXPECTED",
            remaining: "REMAINING",
            end: "END",
            duration: "DURATION",
            confidence: "Confidence",
            profile: "Profile",
            learned: "Learned cycles"
        },
        nl: {
            title: "VOORSPELLING",
            start: "START",
            expected: "VERWACHT",
            remaining: "RESTEREND",
            end: "EINDE",
            duration: "DUUR",
            confidence: "Zekerheid",
            profile: "Profiel",
            learned: "Geleerde cycli"
        },
        de: {
            title: "PROGNOSE",
            start: "START",
            expected: "ERWARTET",
            remaining: "RESTZEIT",
            end: "ENDE",
            duration: "DAUER",
            confidence: "Sicherheit",
            profile: "Profil",
            learned: "Gelernte Zyklen"
        },
        fr: {
            title: "PRÉVISION",
            start: "DÉBUT",
            expected: "PRÉVU",
            remaining: "RESTANT",
            end: "FIN",
            duration: "DURÉE",
            confidence: "Confiance",
            profile: "Profil",
            learned: "Cycles appris"
        },
        ru: {
            title: "ПРОГНОЗ",
            start: "СТАРТ",
            expected: "ОЖИДАЕТСЯ",
            remaining: "ОСТАЛОСЬ",
            end: "КОНЕЦ",
            duration: "ДЛИТЕЛЬНОСТЬ",
            confidence: "Уверенность",
            profile: "Профиль",
            learned: "Изучено циклов"
        },
        pt: {
            title: "PREVISÃO",
            start: "INÍCIO",
            expected: "PREVISTO",
            remaining: "RESTANTE",
            end: "FIM",
            duration: "DURAÇÃO",
            confidence: "Confiança",
            profile: "Perfil",
            learned: "Ciclos aprendidos"
        },
        el: {
            title: "ΠΡΟΒΛΕΨΗ",
            start: "ΕΝΑΡΞΗ",
            expected: "ΑΝΑΜΕΝΕΤΑΙ",
            remaining: "ΑΠΟΜΕΝΕΙ",
            end: "ΤΕΛΟΣ",
            duration: "ΔΙΑΡΚΕΙΑ",
            confidence: "Βεβαιότητα",
            profile: "Προφίλ",
            learned: "Κύκλοι μάθησης"
        }
    };

    function validState(entity) {
        if (!entity) return false;
        const state = String(entity.state ?? "").trim();
        return state !== "" && !["unknown", "unavailable", "none", "null"].includes(state.toLowerCase());
    }

    function language(card) {
        const configured = String(card?._config?.language || "auto").toLowerCase();
        if (configured !== "auto" && STRINGS[configured]) return configured;
        const haLanguage = String(card?._hass?.locale?.language || card?._hass?.language || "en").toLowerCase();
        if (STRINGS[haLanguage]) return haLanguage;
        const short = haLanguage.split(/[-_]/)[0];
        return STRINGS[short] ? short : "en";
    }

    function strings(card) {
        return STRINGS[language(card)] || STRINGS.en;
    }

    function configured(card) {
        const c = card?._config || {};
        return Boolean(
            c.expected_end_entity ||
            c.last_end_entity ||
            c.confidence_entity ||
            c.profile_entity ||
            c.learned_cycles_entity
        );
    }

    function entity(card, entityId) {
        if (!entityId || !card?._hass?.states) return undefined;
        return card._hass.states[entityId];
    }

    function timeValue(card, entityId) {
        const e = entity(card, entityId);
        if (!validState(e)) return "—";
        const parsed = new Date(e.state);
        if (Number.isNaN(parsed.getTime())) return String(e.state);
        try {
            return new Intl.DateTimeFormat(card?._hass?.locale?.language || undefined, {
                hour: "2-digit",
                minute: "2-digit"
            }).format(parsed);
        } catch (_) {
            return parsed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
        }
    }

    function remainingValue(card) {
        try {
            if (typeof card._remainingMinutes === "function" && typeof card._fmtRemaining === "function") {
                const minutes = card._remainingMinutes();
                return card._fmtRemaining(minutes) || "—";
            }
        } catch (_) {
            // Fall through to a conservative raw-state display.
        }
        const e = entity(card, card?._config?.remaining_entity);
        return validState(e) ? String(e.state) : "—";
    }

    function durationValue(card) {
        const e = entity(card, card?._config?.duration_entity);
        if (!validState(e)) return "—";
        try {
            if (typeof card._fmtDuration === "function") {
                const d = card._fmtDuration(e.state);
                if (d) return d.unit ? String(d.value) + " " + String(d.unit) : String(d.value);
            }
        } catch (_) {
            // Fall through to raw state.
        }
        return String(e.state);
    }

    function confidenceValue(card) {
        const e = entity(card, card?._config?.confidence_entity);
        if (!validState(e)) return "—";
        const raw = String(e.state);
        const unit = String(e.attributes?.unit_of_measurement || "").trim();
        if (unit) return raw + " " + unit;
        return /^-?\d+(?:[.,]\d+)?$/.test(raw) ? raw + "%" : raw;
    }

    function rawValue(card, entityId) {
        const e = entity(card, entityId);
        return validState(e) ? String(e.state) : "—";
    }

    function addMoreInfo(card, element, entityId) {
        if (!element || !entityId || typeof card._moreInfo !== "function") return;
        element.classList.add("alp-clickable");
        element.addEventListener("click", () => card._moreInfo(entityId));
    }

    function createCell(root, key, label) {
        const item = document.createElement("div");
        item.className = "alp-item";
        item.id = "alp-" + key;

        const lab = document.createElement("div");
        lab.className = "alp-label";
        lab.textContent = label;

        const value = document.createElement("div");
        value.className = "alp-value";
        value.id = "alp-" + key + "-value";
        value.textContent = "—";

        item.append(lab, value);
        return item;
    }

    function install(card) {
        if (!configured(card)) return;

        const root = card.shadowRoot;
        if (!root || root.getElementById("alp-predictor-panel")) return;

        const anchor = root.getElementById("lastCycle");
        if (!anchor) {
            console.warn("[ALP extension] Compatible insertion point not found; original card left untouched.");
            return;
        }

        const t = strings(card);
        const style = document.createElement("style");
        style.id = "alp-predictor-style";
        style.textContent = [
            ".alp-panel{margin-top:12px;padding:14px;border-radius:14px;background:var(--wm-panel-bg);border:1px solid var(--wm-panel-border);box-shadow:var(--wm-panel-shadow);}",
            ".alp-title{font-size:11px;letter-spacing:.12em;font-weight:700;color:var(--wm-label);margin-bottom:11px;}",
            ".alp-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;}",
            ".alp-item{min-width:0;text-align:center;padding:5px 2px;border-right:1px solid var(--wm-divider);}",
            ".alp-item:last-child{border-right:0;}",
            ".alp-label{font-size:9px;letter-spacing:.06em;font-weight:700;color:var(--wm-label);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}",
            ".alp-value{margin-top:4px;font-size:14px;font-weight:700;color:var(--wm-text);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}",
            ".alp-meta{display:flex;flex-wrap:wrap;gap:7px 14px;margin-top:11px;padding-top:10px;border-top:1px solid var(--wm-divider);font-size:11px;color:var(--wm-muted);}",
            ".alp-meta strong{color:var(--wm-text);font-weight:700;}",
            ".alp-clickable{cursor:pointer;}",
            ".xnarrow .alp-grid,.narrow .alp-grid{grid-template-columns:repeat(3,minmax(0,1fr));}",
            ".xnarrow .alp-item,.narrow .alp-item{border-right:0;border-bottom:1px solid var(--wm-divider);padding:7px 2px;}",
            "@media(max-width:360px){.alp-grid{grid-template-columns:repeat(2,minmax(0,1fr));}}"
        ].join("");

        const panel = document.createElement("div");
        panel.className = "alp-panel";
        panel.id = "alp-predictor-panel";

        const title = document.createElement("div");
        title.className = "alp-title";
        title.id = "alp-title";
        title.textContent = t.title;

        const grid = document.createElement("div");
        grid.className = "alp-grid";
        grid.append(
            createCell(root, "start", t.start),
            createCell(root, "expected", t.expected),
            createCell(root, "remaining", t.remaining),
            createCell(root, "end", t.end),
            createCell(root, "duration", t.duration)
        );

        const meta = document.createElement("div");
        meta.className = "alp-meta";
        meta.id = "alp-meta";
        meta.innerHTML =
            '<span id="alp-confidence-wrap">' + t.confidence + ': <strong id="alp-confidence-value">—</strong></span>' +
            '<span id="alp-profile-wrap">' + t.profile + ': <strong id="alp-profile-value">—</strong></span>' +
            '<span id="alp-learned-wrap">' + t.learned + ': <strong id="alp-learned-value">—</strong></span>';

        panel.append(title, grid, meta);
        anchor.insertAdjacentElement("afterend", panel);
        root.appendChild(style);

        const c = card._config || {};
        addMoreInfo(card, root.getElementById("alp-start"), c.last_wash_entity);
        addMoreInfo(card, root.getElementById("alp-expected"), c.expected_end_entity);
        addMoreInfo(card, root.getElementById("alp-remaining"), c.remaining_entity);
        addMoreInfo(card, root.getElementById("alp-end"), c.last_end_entity);
        addMoreInfo(card, root.getElementById("alp-duration"), c.duration_entity);
        addMoreInfo(card, root.getElementById("alp-confidence-wrap"), c.confidence_entity);
        addMoreInfo(card, root.getElementById("alp-profile-wrap"), c.profile_entity);
        addMoreInfo(card, root.getElementById("alp-learned-wrap"), c.learned_cycles_entity);
    }

    function setText(root, id, value) {
        const el = root?.getElementById(id);
        if (el) el.textContent = value;
    }

    function show(root, id, visible) {
        const el = root?.getElementById(id);
        if (el) el.style.display = visible ? "" : "none";
    }

    function update(card) {
        if (!configured(card)) return;
        install(card);

        const root = card.shadowRoot;
        if (!root?.getElementById("alp-predictor-panel")) return;

        const c = card._config || {};
        const t = strings(card);
        setText(root, "alp-title", t.title);

        setText(root, "alp-start-value", c.last_wash_entity ? timeValue(card, c.last_wash_entity) : "—");
        setText(root, "alp-expected-value", c.expected_end_entity ? timeValue(card, c.expected_end_entity) : "—");
        setText(root, "alp-remaining-value", c.remaining_entity ? remainingValue(card) : "—");
        setText(root, "alp-end-value", c.last_end_entity ? timeValue(card, c.last_end_entity) : "—");
        setText(root, "alp-duration-value", c.duration_entity ? durationValue(card) : "—");

        setText(root, "alp-confidence-value", c.confidence_entity ? confidenceValue(card) : "—");
        setText(root, "alp-profile-value", c.profile_entity ? rawValue(card, c.profile_entity) : "—");
        setText(root, "alp-learned-value", c.learned_cycles_entity ? rawValue(card, c.learned_cycles_entity) : "—");

        show(root, "alp-start", Boolean(c.last_wash_entity));
        show(root, "alp-expected", Boolean(c.expected_end_entity));
        show(root, "alp-remaining", Boolean(c.remaining_entity));
        show(root, "alp-end", Boolean(c.last_end_entity));
        show(root, "alp-duration", Boolean(c.duration_entity));
        show(root, "alp-confidence-wrap", Boolean(c.confidence_entity));
        show(root, "alp-profile-wrap", Boolean(c.profile_entity));
        show(root, "alp-learned-wrap", Boolean(c.learned_cycles_entity));

        const anyMeta = Boolean(c.confidence_entity || c.profile_entity || c.learned_cycles_entity);
        show(root, "alp-meta", anyMeta);
    }

    async function patch() {
        await customElements.whenDefined(CARD_TAG);

        const Card = customElements.get(CARD_TAG);
        if (!Card?.prototype) return;

        const proto = Card.prototype;
        if (proto[PATCH_FLAG]) return;

        if (typeof proto._build !== "function" || typeof proto._update !== "function") {
            console.warn("[ALP extension] Unsupported Washing Machine Animated Card version; original card left untouched.");
            return;
        }

        const originalBuild = proto._build;
        const originalUpdate = proto._update;

        proto._build = function (...args) {
            const result = originalBuild.apply(this, args);
            try {
                install(this);
            } catch (error) {
                console.warn("[ALP extension] Build extension failed; original card remains active.", error);
            }
            return result;
        };

        proto._update = function (...args) {
            const result = originalUpdate.apply(this, args);
            try {
                update(this);
            } catch (error) {
                console.warn("[ALP extension] Update extension failed; original card remains active.", error);
            }
            return result;
        };

        Object.defineProperty(proto, PATCH_FLAG, {
            configurable: false,
            enumerable: false,
            writable: false,
            value: true
        });

        window.washingMachinePredictorExtension = {
            version: EXTENSION_VERSION,
            card: CARD_TAG,
            active: true
        };

        console.info("[ALP extension] Predictor Extension v" + EXTENSION_VERSION + " loaded.");
    }

    patch().catch((error) => {
        console.warn("[ALP extension] Could not initialize; original card remains untouched.", error);
    });
})();
