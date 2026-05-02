"use strict";

const cp = require("child_process");
const path = require("path");
const vscode = require("vscode");

const ROOT_COMMANDS = ["CUTSCENE", "DURATION", "OFFSET", "ROTATION", "FLAGS", "ASSETS", "TRACK", "SAVE"];
const ASSET_COMMANDS = ["ASSET_MANAGER", "ANIM_MANAGER", "CAMERA", "PROP", "PED", "VEHICLE", "LIGHT", "AUDIO", "SUBTITLE", "FADE", "OVERLAY", "DECAL"];
const TRACK_NAMES = ["LOAD", "CAMERA", "ANIMATION", "OBJECTS", "FADE", "OVERLAYS", "LIGHTS", "SUBTITLES", "AUDIO", "CLEANUP"];
const FLAGS = [
  "PLAYABLE",
  "SECTIONED",
  "STORY_MODE",
  "NONE",
  "FADE_IN_GAME",
  "FADE_OUT_GAME",
  "FADE_IN_CUTSCENE",
  "FADE_OUT_CUTSCENE",
  "SHORT_FADE_OUT",
  "LONG_FADE_OUT",
  "FADE_BETWEEN_SECTIONS",
  "NO_AMBIENT_LIGHTS",
  "NO_VEHICLE_LIGHTS",
  "USE_ONE_AUDIO",
  "MUTE_MUSIC_PLAYER",
  "LEAK_RADIO",
  "TRANSLATE_BONE_IDS",
  "INTERP_CAMERA",
  "IS_SECTIONED",
  "SECTION_BY_CAMERA_CUTS",
  "SECTION_BY_DURATION",
  "SECTION_BY_SPLIT",
  "USE_PARENT_SCALE",
  "USE_ONE_SCENE_ORIENTATION",
  "ENABLE_DEPTH_OF_FIELD",
  "STREAM_PROCESSED",
  "USE_STORY_MODE",
  "USE_IN_GAME_DOF_START",
  "USE_IN_GAME_DOF_END",
  "USE_CATCHUP_CAMERA",
  "USE_BLENDOUT_CAMERA",
  "PART",
  "INTERNAL_CONCAT",
  "EXTERNAL_CONCAT",
  "USE_AUDIO_EVENTS_CONCAT",
  "USE_IN_GAME_DOF_START_SECOND_CUT",
];
const MODEL_OPTIONS = ["MODEL", "YTYP", "ANIM_BASE", "PRESET"];
const LIGHT_PROPERTIES = ["TYPE", "POSITION", "DIRECTION", "COLOR", "INTENSITY", "FALLOFF", "CONE", "INNER_CONE", "CORONA", "FLAGS", "PROPERTY", "STATIC"];
const CAMERA_OPTIONS = ["NAME", "POS", "ROT", "NEAR", "FAR", "MAP_LOD"];
const FADE_OPTIONS = ["VALUE", "COLOR"];
const SUBTITLE_OPTIONS = ["FOR", "LANG"];
const PRESETS = ["COMMON_PROP", "COMMON_PROP_ALT_COMPRESSION", "ALT_EXPORT_A", "ALT_EXPORT_B"];
const LIGHT_TYPES = ["POINT", "SPOT", "DIRECTIONAL"];
const SECTION_END_SNIPPET = {
  END: {
    insert: "END",
    detail: "END",
    documentation: "Closes the current ASSETS or TRACK section. SAVE and new sections must be outside closed blocks.",
  },
};

const ROOT_SNIPPETS = {
  CUTSCENE: {
    insert: "CUTSCENE \"${1:name}\"",
    detail: "CUTSCENE \"name\"",
    documentation: "Declares the cutscene name. This should match the mounted cutscene asset name.",
  },
  DURATION: {
    insert: "DURATION ${1:seconds}",
    detail: "DURATION seconds",
    documentation: "Total cutscene duration in seconds.",
  },
  OFFSET: {
    insert: "OFFSET ${1:x} ${2:y} ${3:z}",
    detail: "OFFSET x y z",
    documentation: "World offset for the cutscene. Order is X, Y, Z.",
  },
  ROTATION: {
    insert: "ROTATION ${1:degrees}",
    detail: "ROTATION degrees",
    documentation: "Root cutscene rotation in degrees.",
  },
  FLAGS: {
    insert: "FLAGS ${1:PLAYABLE} ${2:SECTIONED} ${3:STORY_MODE}",
    detail: "FLAGS flag...",
    documentation: "Packed cutscene flags. Use PLAYABLE as a safe preset, or combine explicit CutSceneFlags names.",
  },
  ASSETS: {
    insert: "ASSETS\n\t${1:ASSET_MANAGER assets}\nEND",
    detail: "ASSETS ... END",
    documentation: "Starts the asset declaration block. It must be closed with END before TRACK or SAVE.",
  },
  TRACK: {
    insert: "TRACK ${1|LOAD,CAMERA,ANIMATION,OBJECTS,FADE,OVERLAYS,LIGHTS,SUBTITLES,AUDIO,CLEANUP|}\n\t${2:0.000 }\nEND",
    detail: "TRACK name ... END",
    documentation: "Starts a timeline track. Following lines use: time command args... The track must be closed with END.",
  },
  SAVE: {
    insert: "SAVE \"${1:name.cut}\"",
    detail: "SAVE \"path.cut\"",
    documentation: "Output .cut path. Relative paths are resolved from the .cuts file folder.",
  },
};

const ASSET_SNIPPETS = {
  ASSET_MANAGER: {
    insert: "ASSET_MANAGER ${1:assets}",
    detail: "ASSET_MANAGER name",
    documentation: "Declares the asset manager object used by load/unload events.",
  },
  ANIM_MANAGER: {
    insert: "ANIM_MANAGER ${1:anims}",
    detail: "ANIM_MANAGER name",
    documentation: "Declares the animation manager object used by YCD load and animation binding events.",
  },
  CAMERA: {
    insert: "CAMERA ${1:cam_main}",
    detail: "CAMERA name",
    documentation: "Declares a camera object that CAMERA CUT events can target.",
  },
  PROP: {
    insert: "PROP ${1:name}:\n\tMODEL \"${2:model_name}\"\n\tYTYP \"${3:ytyp_name}\"",
    detail: "PROP name: + MODEL/YTYP lines",
    documentation: "Declares a streamed prop block. The colon marks that MODEL, YTYP, ANIM_BASE and PRESET belong to this prop.",
  },
  PED: {
    insert: "PED ${1:name}:\n\tMODEL \"${2:model_name}\"\n\tYTYP \"${3:ytyp_name}\"",
    detail: "PED name: + MODEL/YTYP lines",
    documentation: "Declares a cutscene ped block. The colon marks that following model options belong to this ped.",
  },
  VEHICLE: {
    insert: "VEHICLE ${1:name}:\n\tMODEL \"${2:model_name}\"\n\tYTYP \"${3:ytyp_name}\"",
    detail: "VEHICLE name: + MODEL/YTYP lines",
    documentation: "Declares a cutscene vehicle block. The colon marks that following model options belong to this vehicle.",
  },
  LIGHT: {
    insert: "LIGHT ${1:key_light}:\n\tTYPE ${2|POINT,SPOT,DIRECTIONAL|}\n\tPOSITION ${3:x} ${4:y} ${5:z}\n\tCOLOR ${6:#ffffff}\n\tINTENSITY ${7:1.0}",
    detail: "LIGHT name:",
    documentation: "Declares a cutscene light block. The colon marks that following light properties belong to this light.",
  },
  AUDIO: {
    insert: "AUDIO ${1:audio}",
    detail: "AUDIO name",
    documentation: "Declares an audio object used by AUDIO track events.",
  },
  SUBTITLE: {
    insert: "SUBTITLE ${1:subtitles}",
    detail: "SUBTITLE name",
    documentation: "Declares a subtitle object used by SUBTITLES track events.",
  },
  FADE: {
    insert: "FADE ${1:screen}",
    detail: "FADE name",
    documentation: "Declares a screen fade object used by FADE track events.",
  },
  OVERLAY: {
    insert: "OVERLAY ${1:title_card}",
    detail: "OVERLAY name",
    documentation: "Declares an overlay object used by OVERLAYS load/show/hide events.",
  },
  DECAL: {
    insert: "DECAL ${1:decal}",
    detail: "DECAL name",
    documentation: "Declares a decal object for decal events.",
  },
};

const TRACK_SNIPPETS = Object.fromEntries(
  TRACK_NAMES.map((name) => [
    name,
    {
      insert: name,
      detail: `TRACK ${name}`,
      documentation: trackDocumentation(name),
    },
  ])
);

const EVENT_SNIPPETS = {
  LOAD: {
    SCENE: { insert: "${1:0.000} SCENE \"${2:scene_name}\"", detail: "time SCENE \"name\"", documentation: "Loads a cutscene scene name through the asset manager." },
    MODELS: { insert: "${1:0.000} MODELS ${2:asset_name}", detail: "time MODELS object...", documentation: "Loads one or more declared prop/ped/vehicle objects." },
    UNLOAD_MODELS: { insert: "${1:0.000} UNLOAD_MODELS ${2:asset_name}", detail: "time UNLOAD_MODELS object...", documentation: "Unloads one or more declared model objects." },
    ANIM_DICT: { insert: "${1:0.000} ANIM_DICT \"${2:ycd_name}\"", detail: "time ANIM_DICT \"name\"", documentation: "Loads a YCD animation dictionary." },
    UNLOAD_ANIM_DICT: { insert: "${1:0.000} UNLOAD_ANIM_DICT \"${2:ycd_name}\"", detail: "time UNLOAD_ANIM_DICT \"name\"", documentation: "Unloads a YCD animation dictionary." },
    SUBTITLES: { insert: "${1:0.000} SUBTITLES \"${2:subtitle_dict}\"", detail: "time SUBTITLES \"name\"", documentation: "Loads subtitle text entries by name." },
    UNLOAD_SUBTITLES: { insert: "${1:0.000} UNLOAD_SUBTITLES \"${2:subtitle_dict}\"", detail: "time UNLOAD_SUBTITLES \"name\"", documentation: "Unloads subtitle text entries." },
    LOAD_OVERLAYS: { insert: "${1:0.000} LOAD_OVERLAYS ${2:overlay_name}", detail: "time LOAD_OVERLAYS overlay...", documentation: "Loads declared overlay objects." },
    UNLOAD_OVERLAYS: { insert: "${1:0.000} UNLOAD_OVERLAYS ${2:overlay_name}", detail: "time UNLOAD_OVERLAYS overlay...", documentation: "Unloads declared overlay objects." },
  },
  CAMERA: {
    CUT: {
      insert: "${1:0.000} CUT ${2:camera}:\n\tNAME \"${3:cut_name}\"\n\tPOS ${4:x} ${5:y} ${6:z}\n\tROT ${7:pitch} ${8:yaw} ${9:roll}\n\tNEAR ${10:0.05}\n\tFAR ${11:1000}",
      detail: "time CUT camera: + camera property lines",
      documentation: "Switches to a camera. The colon marks that NAME, POS, ROT, NEAR and FAR belong to this cut. ROT is Euler XYZ degrees.",
    },
    DRAW_DISTANCE: { insert: "${1:0.000} DRAW_DISTANCE ${2:camera} ${3:distance}", detail: "time DRAW_DISTANCE camera value", documentation: "Sets camera draw distance." },
  },
  ANIMATION: {
    PLAY: { insert: "${1:0.033} PLAY ${2:object}", detail: "time PLAY object", documentation: "Binds animation to a declared object. The object metadata decides the clip base." },
    STOP: { insert: "${1:0.000} STOP ${2:object}", detail: "time STOP object", documentation: "Clears animation from a declared object." },
  },
  OBJECTS: {
    SHOW: { insert: "${1:0.000} SHOW ${2:object}", detail: "time SHOW object...", documentation: "Shows one or more declared objects." },
    HIDE: { insert: "${1:0.000} HIDE ${2:object}", detail: "time HIDE object...", documentation: "Hides one or more declared objects." },
    ATTACH: { insert: "${1:0.000} ATTACH ${2:object} TO \"${3:attachment_name}\"", detail: "time ATTACH object TO \"attachment\"", documentation: "Sets an attachment name for an object." },
  },
  FADE: {
    IN: { insert: "${1:0.000} IN ${2:screen} VALUE ${3:0.0} COLOR ${4:0xff000000}", detail: "time IN fade VALUE value COLOR argb", documentation: "Fade in event. COLOR is packed ARGB, for example 0xff000000." },
    OUT: { insert: "${1:0.000} OUT ${2:screen} VALUE ${3:1.0} COLOR ${4:0xff000000}", detail: "time OUT fade VALUE value COLOR argb", documentation: "Fade out event. COLOR is packed ARGB, for example 0xff000000." },
    FADE_IN: { insert: "${1:0.000} FADE_IN ${2:screen} VALUE ${3:0.0} COLOR ${4:0xff000000}", detail: "time FADE_IN fade VALUE value COLOR argb", documentation: "Alias for IN." },
    FADE_OUT: { insert: "${1:0.000} FADE_OUT ${2:screen} VALUE ${3:1.0} COLOR ${4:0xff000000}", detail: "time FADE_OUT fade VALUE value COLOR argb", documentation: "Alias for OUT." },
  },
  OVERLAYS: {
    LOAD: { insert: "${1:0.000} LOAD ${2:overlay}", detail: "time LOAD overlay...", documentation: "Loads declared overlay objects." },
    UNLOAD: { insert: "${1:0.000} UNLOAD ${2:overlay}", detail: "time UNLOAD overlay...", documentation: "Unloads declared overlay objects." },
    SHOW: { insert: "${1:0.000} SHOW ${2:overlay}", detail: "time SHOW overlay...", documentation: "Shows declared overlay objects." },
    HIDE: { insert: "${1:0.000} HIDE ${2:overlay}", detail: "time HIDE overlay...", documentation: "Hides declared overlay objects." },
  },
  LIGHTS: {
    ENABLE: { insert: "${1:0.000} ENABLE ${2:light}", detail: "time ENABLE light", documentation: "Enables a cutscene light." },
    DISABLE: { insert: "${1:0.000} DISABLE ${2:light}", detail: "time DISABLE light", documentation: "Disables a cutscene light." },
    ON: { insert: "${1:0.000} ON ${2:light}", detail: "time ON light", documentation: "Alias for ENABLE." },
    OFF: { insert: "${1:0.000} OFF ${2:light}", detail: "time OFF light", documentation: "Alias for DISABLE." },
  },
  SUBTITLES: {
    SHOW: { insert: "${1:0.000} SHOW \"${2:SUB_KEY}\" FOR ${3:3.0}", detail: "time SHOW \"key\" FOR seconds", documentation: "Shows a subtitle text key for a duration in seconds." },
    HIDE: { insert: "${1:0.000} HIDE \"${2:SUB_KEY}\"", detail: "time HIDE \"key\"", documentation: "Hides a subtitle text key." },
  },
  AUDIO: {
    LOAD: { insert: "${1:0.000} LOAD \"${2:audio_bank}\"", detail: "time LOAD \"name\"", documentation: "Loads an audio bank/name." },
    UNLOAD: { insert: "${1:0.000} UNLOAD \"${2:audio_bank}\"", detail: "time UNLOAD \"name\"", documentation: "Unloads an audio bank/name." },
    PLAY: { insert: "${1:0.000} PLAY \"${2:cue_name}\"", detail: "time PLAY \"cue\"", documentation: "Plays an audio cue/name." },
    STOP: { insert: "${1:0.000} STOP \"${2:cue_name}\"", detail: "time STOP \"cue\"", documentation: "Stops an audio cue/name." },
  },
  CLEANUP: {
    UNLOAD_MODELS: { insert: "${1:0.000} UNLOAD_MODELS ${2:asset_name}", detail: "time UNLOAD_MODELS object...", documentation: "Cleanup unload for model objects." },
    UNLOAD_ANIM_DICT: { insert: "${1:0.000} UNLOAD_ANIM_DICT \"${2:ycd_name}\"", detail: "time UNLOAD_ANIM_DICT \"name\"", documentation: "Cleanup unload for animation dictionary." },
    UNLOAD_SUBTITLES: { insert: "${1:0.000} UNLOAD_SUBTITLES \"${2:subtitle_dict}\"", detail: "time UNLOAD_SUBTITLES \"name\"", documentation: "Cleanup unload for subtitle entries." },
    UNLOAD_SCENE: { insert: "${1:0.000} UNLOAD_SCENE \"${2:scene_name}\"", detail: "time UNLOAD_SCENE \"name\"", documentation: "Cleanup unload for scene name." },
    UNLOAD_OVERLAYS: { insert: "${1:0.000} UNLOAD_OVERLAYS ${2:overlay_name}", detail: "time UNLOAD_OVERLAYS overlay...", documentation: "Cleanup unload for overlay objects." },
  },
};

const OPTION_DOCS = {
  MODEL: "Drawable/archetype/model name used by the streamed object.",
  YTYP: "YTYP/typeFile name where the archetype comes from.",
  ANIM_BASE: "Animation clip base used to calculate AnimStreamingBase.",
  PRESET: "Known cutscene animation metadata preset.",
  TYPE: "Light type.",
  POSITION: "Position vector. Order is X, Y, Z.",
  POS: "Position vector. Order is X, Y, Z.",
  DIRECTION: "Direction vector. Order is X, Y, Z.",
  DIR: "Direction vector. Order is X, Y, Z.",
  COLOR: "CSS-like color. Accepts red, #ff8800, #f80, rgb(...), hsl(...) or numeric RGB.",
  COLOUR: "CSS-like color. Accepts red, #ff8800, #f80, rgb(...), hsl(...) or numeric RGB.",
  INTENSITY: "Light intensity.",
  FALLOFF: "Light falloff distance.",
  CONE: "Outer cone angle in degrees.",
  INNER_CONE: "Inner cone angle in degrees.",
  CORONA: "Corona size and intensity.",
  FLAGS: "Flags list.",
  PROPERTY: "Light property enum name.",
  STATIC: "Boolean static flag.",
  NAME: "Name/hash label for this event payload.",
  ROT: "Euler XYZ rotation in degrees.",
  ROTATION: "Euler XYZ rotation in degrees.",
  NEAR: "Near clip/draw distance. Keep sane, for example 0.05.",
  FAR: "Far clip/draw distance. Avoid absurdly large values.",
  MAP_LOD: "Map LOD scale value.",
  FOR: "Duration in seconds.",
  LANG: "Subtitle language id.",
  LANGUAGE: "Subtitle language id.",
  TO: "Attachment target name.",
  VALUE: "Numeric event value.",
  COLOR_FADE: "Packed ARGB color, for example 0xff000000.",
};

function activate(context) {
  const output = vscode.window.createOutputChannel("FiveFury CutScript");

  context.subscriptions.push(output);
  context.subscriptions.push(vscode.commands.registerCommand("fivefuryCuts.compile", () => compileActiveCutScript(output)));
  context.subscriptions.push(
    vscode.languages.registerCompletionItemProvider(
      { language: "cutscript", scheme: "file" },
      new CutScriptCompletionProvider(),
      " ",
      "\t",
      ":"
    )
  );
  context.subscriptions.push(vscode.languages.registerHoverProvider({ language: "cutscript", scheme: "file" }, new CutScriptHoverProvider()));
}

function deactivate() {}

class CutScriptCompletionProvider {
  provideCompletionItems(document, position) {
    try {
      const line = document.lineAt(position).text.slice(0, position.character);
      const indentation = currentIndentation(line);
      const trimmed = line.trimStart();
      const lineEndsWithWhitespace = /\s$/.test(line);
      const context = getDocumentContext(document, position.line);

      if (!trimmed) {
        if (context.section === "ASSETS") {
          return assetBlockCompletionItems(context, indentation);
        }
        if (context.section === "TRACK") {
          return trackBlockCompletionItems(context, indentation);
        }
        return snippetsFromMap(ROOT_SNIPPETS, vscode.CompletionItemKind.Keyword, indentation);
      }

      const tokens = splitWords(trimmed);
      const upperTokens = tokens.map((token) => token.toUpperCase());
      const first = upperTokens[0] || "";
      const previous = upperTokens[upperTokens.length - 2] || "";
      const contextualArguments = contextualArgumentItems(context, tokens, upperTokens, lineEndsWithWhitespace, indentation);
      if (contextualArguments) {
        return contextualArguments;
      }

      if (first === "TRACK") {
        return lineEndsWithWhitespace
          ? snippetsFromMap(TRACK_SNIPPETS, vscode.CompletionItemKind.EnumMember, indentation)
          : [snippet("TRACK", ROOT_SNIPPETS.TRACK.insert, vscode.CompletionItemKind.Keyword, ROOT_SNIPPETS.TRACK.detail, ROOT_SNIPPETS.TRACK.documentation, indentation)];
      }
      if (first === "FLAGS") {
        return lineEndsWithWhitespace
          ? flagItems()
          : [snippet("FLAGS", ROOT_SNIPPETS.FLAGS.insert, vscode.CompletionItemKind.Keyword, ROOT_SNIPPETS.FLAGS.detail, ROOT_SNIPPETS.FLAGS.documentation, indentation)];
      }
      if (context.section === "ASSETS") {
        return assetCompletionItems(first, previous, context, indentation);
      }
      if (context.section === "TRACK") {
        return eventCompletionItems(context.track, first, previous, context, indentation);
      }
      return snippetsFromMap(ROOT_SNIPPETS, vscode.CompletionItemKind.Keyword, indentation);
    } catch (error) {
      console.error("FiveFury CutScript completion failed", error);
      return [];
    }
  }
}

class CutScriptHoverProvider {
  provideHover(document, position) {
    const range = document.getWordRangeAtPosition(position, /[A-Za-z_]+/);
    if (!range) {
      return null;
    }
    const word = document.getText(range).toUpperCase();
    const context = getDocumentContext(document, position.line);
    const rootDefinition = ROOT_SNIPPETS[word];
    const assetDefinition = ASSET_SNIPPETS[word];
    const eventDefinition = EVENT_SNIPPETS[context.track]?.[word];
    const optionDocumentation = OPTION_DOCS[word];

    if (rootDefinition) {
      return hover(rootDefinition.detail, rootDefinition.documentation);
    }
    if (assetDefinition) {
      return hover(assetDefinition.detail, assetDefinition.documentation);
    }
    if (eventDefinition) {
      return hover(eventDefinition.detail, eventDefinition.documentation);
    }
    if (optionDocumentation) {
      return hover(optionDetail(word), optionDocumentation);
    }
    if (FLAGS.includes(word)) {
      return hover("CutScene flag", word === "PLAYABLE" ? "Convenience preset for a normal playable cutscene." : "CutSceneFlags enum value.");
    }
    if (TRACK_NAMES.includes(word)) {
      return hover(`TRACK ${word}`, trackDocumentation(word));
    }
    return null;
  }
}

function contextualArgumentItems(context, tokens, upperTokens, lineEndsWithWhitespace, indentation) {
  const first = upperTokens[0] || "";
  if (first === "TRACK" && lineEndsWithWhitespace) {
    return snippetsFromMap(TRACK_SNIPPETS, vscode.CompletionItemKind.EnumMember, indentation);
  }
  if (context.section === "ROOT" && ROOT_COMMANDS.includes(first) && lineEndsWithWhitespace) {
    return rootArgumentItems(first, indentation);
  }
  if (context.section === "ASSETS" && lineEndsWithWhitespace) {
    return assetArgumentItems(tokens, upperTokens, context, indentation);
  }
  if (context.section === "TRACK") {
    return trackArgumentItems(context.track, tokens, upperTokens, context, lineEndsWithWhitespace, indentation);
  }
  return null;
}

function rootArgumentItems(command, indentation) {
  switch (command) {
    case "CUTSCENE":
      return [snippet("cutscene name", "\"${1:name}\"", vscode.CompletionItemKind.Value, "CUTSCENE \"name\"", "Name of the cutscene asset.", indentation)];
    case "DURATION":
      return [snippet("seconds", "${1:seconds}", vscode.CompletionItemKind.Value, "DURATION seconds", "Total cutscene duration in seconds.", indentation)];
    case "OFFSET":
      return [snippet("x y z", "${1:x} ${2:y} ${3:z}", vscode.CompletionItemKind.Value, "OFFSET x y z", "World offset. Order is X, Y, Z.", indentation)];
    case "ROTATION":
      return [snippet("degrees", "${1:degrees}", vscode.CompletionItemKind.Value, "ROTATION degrees", "Root cutscene rotation in degrees.", indentation)];
    case "FLAGS":
      return flagItems();
    case "TRACK":
      return snippetsFromMap(TRACK_SNIPPETS, vscode.CompletionItemKind.EnumMember, indentation);
    case "SAVE":
      return [snippet("output path", "\"${1:name.cut}\"", vscode.CompletionItemKind.File, "SAVE \"path.cut\"", "Output .cut path.", indentation)];
    default:
      return null;
  }
}

function assetArgumentItems(tokens, upperTokens, context, indentation) {
  const command = upperTokens[0] || "";
  const previous = upperTokens[upperTokens.length - 1] || "";
  if (["ASSET_MANAGER", "ANIM_MANAGER", "CAMERA", "AUDIO", "SUBTITLE", "FADE", "OVERLAY", "DECAL"].includes(command) && tokens.length === 1) {
    return [snippet("name", "${1:name}", vscode.CompletionItemKind.Value, `${command} name`, "Object name used by later timeline events.", indentation)];
  }
  if (["PROP", "PED", "VEHICLE"].includes(command)) {
    if (tokens.length === 1) {
      return [snippet("name + model block", "${1:name}:\n\tMODEL \"${2:model_name}\"\n\tYTYP \"${3:ytyp_name}\"", vscode.CompletionItemKind.Value, `${command} name: + MODEL/YTYP lines`, "Declares a streamed object block with readable model/type-file properties.", indentation)];
    }
    if (["MODEL", "YTYP", "ANIM_BASE"].includes(previous)) {
      return [snippet(previous.toLowerCase(), "\"${1:value}\"", vscode.CompletionItemKind.Value, `${previous} "value"`, OPTION_DOCS[previous], indentation)];
    }
    if (previous === "PRESET") {
      return documentedItems(PRESETS, vscode.CompletionItemKind.EnumMember, "Animation preset", "Known cutscene animation metadata preset.");
    }
    return optionItems(MODEL_OPTIONS);
  }
  if (command === "LIGHT") {
    if (tokens.length === 1) {
      return [snippet("name + light block", "${1:key_light}:\n\tTYPE ${2|POINT,SPOT,DIRECTIONAL|}\n\tPOSITION ${3:x} ${4:y} ${5:z}\n\tCOLOR ${6:#ffffff}\n\tINTENSITY ${7:1.0}", vscode.CompletionItemKind.Value, "LIGHT name: + property lines", "Cutscene light object block.", indentation)];
    }
    return optionItems(LIGHT_PROPERTIES);
  }
  if (LIGHT_PROPERTIES.includes(command)) {
    return lightPropertyArgumentItems(command, indentation);
  }
  if (["PROP", "PED", "VEHICLE"].includes(context.assetBlock) && MODEL_OPTIONS.includes(command)) {
    return modelPropertyArgumentItems(command, indentation);
  }
  if (context.assetBlock === "LIGHT" && LIGHT_PROPERTIES.includes(command)) {
    return lightPropertyArgumentItems(command, indentation);
  }
  return null;
}

function modelPropertyArgumentItems(command, indentation) {
  if (["MODEL", "YTYP", "ANIM_BASE"].includes(command)) {
    return [snippet(command.toLowerCase(), "\"${1:value}\"", vscode.CompletionItemKind.Value, `${command} "value"`, OPTION_DOCS[command], indentation)];
  }
  if (command === "PRESET") {
    return documentedItems(PRESETS, vscode.CompletionItemKind.EnumMember, "Animation preset", "Known cutscene animation metadata preset.");
  }
  return optionItems(MODEL_OPTIONS);
}

function lightPropertyArgumentItems(command, indentation) {
  switch (command) {
    case "TYPE":
      return documentedItems(LIGHT_TYPES, vscode.CompletionItemKind.EnumMember, "Light type", "Cutscene light type.");
    case "POSITION":
    case "POS":
    case "DIRECTION":
    case "DIR":
      return [snippet("x y z", "${1:x} ${2:y} ${3:z}", vscode.CompletionItemKind.Value, `${command} x y z`, "Vector order is X, Y, Z.", indentation)];
    case "COLOR":
    case "COLOUR":
      return [snippet("css color", "${1:#ffffff}", vscode.CompletionItemKind.Color, `${command} CSS color`, "CSS-like color, for example red, #ff8800, rgb(255 128 0), or hsl(30 100% 50%).", indentation)];
    case "CORONA":
      return [snippet("size intensity", "${1:size} ${2:intensity}", vscode.CompletionItemKind.Value, "CORONA size intensity", "Corona sprite size and intensity.", indentation)];
    case "FLAGS":
      return documentedItems(["NONE", "CAST_SHADOWS", "CUTSCENE_ONLY"], vscode.CompletionItemKind.EnumMember, "Light flag", "Cut light flag.");
    case "STATIC":
      return documentedItems(["true", "false"], vscode.CompletionItemKind.Value, "boolean", "Boolean value.");
    default:
      return [snippet("value", "${1:value}", vscode.CompletionItemKind.Value, `${command} value`, OPTION_DOCS[command] || "Property value.", indentation)];
  }
}

function trackArgumentItems(track, tokens, upperTokens, context, lineEndsWithWhitespace, indentation) {
  if (!tokens.length) {
    return null;
  }
  const assets = context.assets;
  const first = upperTokens[0] || "";
  const isTimelineLine = isNumericToken(first);
  if (!isTimelineLine) {
    if (track === "CAMERA" && context.cameraCutBlock && CAMERA_OPTIONS.includes(first) && lineEndsWithWhitespace) {
      return eventOptionArgumentItems(first, context, indentation);
    }
    return null;
  }
  if (tokens.length === 1 && lineEndsWithWhitespace) {
    return eventCommandItems(track, indentation);
  }
  const command = upperTokens[1] || "";
  const previous = upperTokens[upperTokens.length - 1] || "";
  if (tokens.length === 2 && lineEndsWithWhitespace) {
    return eventArgumentItems(track, command, context, indentation);
  }
  if (lineEndsWithWhitespace) {
    const optionArgs = eventOptionArgumentItems(previous, context, indentation);
    if (optionArgs) {
      return optionArgs;
    }
  }
  return null;
}

function eventCommandItems(track, indentation) {
  const definitions = EVENT_SNIPPETS[track] || {};
  return Object.entries(definitions).map(([label, definition]) => {
    const insert = withoutLeadingTimeSnippet(definition.insert);
    return snippet(label, insert, vscode.CompletionItemKind.Function, definition.detail.replace(/^time\s+/, ""), definition.documentation, indentation);
  });
}

function eventArgumentItems(track, command, context, indentation) {
  const assets = context.assets;
  const modelAssets = [...assets.prop, ...assets.ped, ...assets.vehicle];
  if (track === "LOAD") {
    switch (command) {
      case "SCENE":
      case "UNLOAD_SCENE":
        return sceneNameItems(context, "Scene name loaded by this cutscene.", indentation);
      case "MODELS":
      case "UNLOAD_MODELS":
        return assetItems(modelAssets);
      case "ANIM_DICT":
      case "UNLOAD_ANIM_DICT":
        return sceneNameItems(context, "YCD animation dictionary name. Usually the cutscene name.", indentation);
      case "SUBTITLES":
      case "UNLOAD_SUBTITLES":
        return sceneNameItems(context, "Subtitle dictionary name. Often matches the cutscene name.", indentation);
      case "LOAD_OVERLAYS":
      case "UNLOAD_OVERLAYS":
        return assetItems(assets.overlay);
      default:
        return [];
    }
  }
  if (track === "CLEANUP") {
    switch (command) {
      case "UNLOAD_SCENE":
      case "UNLOAD_ANIM_DICT":
      case "UNLOAD_SUBTITLES":
        return sceneNameItems(context, "Name to unload. Usually the cutscene name.", indentation);
      case "UNLOAD_MODELS":
        return assetItems(modelAssets);
      case "UNLOAD_OVERLAYS":
        return assetItems(assets.overlay);
      default:
        return [];
    }
  }
  if (track === "CAMERA" && command === "CUT") {
    return [
      ...assetItems(assets.camera),
      snippet("camera cut block", "${1:camera}:\n\tNAME \"${2:cut_name}\"\n\tPOS ${3:x} ${4:y} ${5:z}\n\tROT ${6:pitch} ${7:yaw} ${8:roll}\n\tNEAR ${9:0.05}\n\tFAR ${10:1000}", vscode.CompletionItemKind.Snippet, "camera: + NAME/POS/ROT/NEAR/FAR lines", "Complete camera cut arguments. ROT is Euler XYZ in degrees.", indentation),
    ];
  }
  if (track === "CAMERA" && command === "DRAW_DISTANCE") {
    return [...assetItems(assets.camera), snippet("camera distance", "${1:camera} ${2:distance}", vscode.CompletionItemKind.Snippet, "camera distance", "Camera object and draw distance value.", indentation)];
  }
  if (track === "ANIMATION") {
    return assetItems(modelAssets);
  }
  if (track === "OBJECTS") {
    return assetItems(modelAssets);
  }
  if (track === "LIGHTS") {
    return assetItems(assets.light);
  }
  if (track === "FADE") {
    return [...assetItems(assets.fade), ...optionItems(FADE_OPTIONS)];
  }
  if (track === "OVERLAYS") {
    return assetItems(assets.overlay);
  }
  if (track === "SUBTITLES" && command === "SHOW") {
    return [snippet("subtitle key", "\"${1:SUB_KEY}\" FOR ${2:3.0}", vscode.CompletionItemKind.Snippet, "\"key\" FOR seconds", "Subtitle key and duration in seconds.", indentation)];
  }
  if (track === "AUDIO") {
    return [snippet("name", "\"${1:name}\"", vscode.CompletionItemKind.Value, "\"name\"", "Audio bank or cue name.", indentation)];
  }
  return [];
}

function eventOptionArgumentItems(previous, context, indentation) {
  const assets = context.assets;
  switch (previous) {
    case "NAME":
      return [snippet("name", "\"${1:name}\"", vscode.CompletionItemKind.Value, "NAME \"name\"", "Name/hash label for this event payload.", indentation)];
    case "POS":
    case "POSITION":
      return [snippet("x y z", "${1:x} ${2:y} ${3:z}", vscode.CompletionItemKind.Value, `${previous} x y z`, "Position order is X, Y, Z.", indentation)];
    case "ROT":
    case "ROTATION":
      return [snippet("pitch yaw roll", "${1:pitch} ${2:yaw} ${3:roll}", vscode.CompletionItemKind.Value, `${previous} pitch yaw roll`, "Euler XYZ rotation in degrees.", indentation)];
    case "NEAR":
      return [snippet("near", "${1:0.05}", vscode.CompletionItemKind.Value, "NEAR value", "Near clip/draw distance. Keep sane, for example 0.05.", indentation)];
    case "FAR":
      return [snippet("far", "${1:1000}", vscode.CompletionItemKind.Value, "FAR value", "Far clip/draw distance. Avoid absurd values.", indentation)];
    case "MAP_LOD":
      return [snippet("map lod", "${1:0.0}", vscode.CompletionItemKind.Value, "MAP_LOD value", "Map LOD scale.", indentation)];
    case "VALUE":
      return [snippet("value", "${1:1.0}", vscode.CompletionItemKind.Value, "VALUE number", "Numeric event value.", indentation)];
    case "COLOR":
    case "COLOUR":
      return [snippet("css color", "${1:#000000}", vscode.CompletionItemKind.Color, `${previous} CSS color`, "CSS-like color, for example black, #000, rgba(0 0 0 / 50%), or packed 0xff000000.", indentation)];
    case "FOR":
      return [snippet("seconds", "${1:3.0}", vscode.CompletionItemKind.Value, "FOR seconds", "Duration in seconds.", indentation)];
    case "LANG":
    case "LANGUAGE":
      return [snippet("language id", "${1:-1}", vscode.CompletionItemKind.Value, `${previous} id`, "Subtitle language id. -1 means default.", indentation)];
    case "TO":
      return [snippet("attachment", "\"${1:attachment_name}\"", vscode.CompletionItemKind.Value, "TO \"attachment_name\"", "Attachment name/hash label.", indentation)];
    default:
      return null;
  }
}

function assetBlockCompletionItems(context, indentation) {
  if (["PROP", "PED", "VEHICLE"].includes(context.assetBlock)) {
    return [...optionItems(MODEL_OPTIONS), ...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword)];
  }
  if (context.assetBlock === "LIGHT") {
    return [...optionItems(LIGHT_PROPERTIES), ...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword)];
  }
  return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...snippetsFromMap(ASSET_SNIPPETS, vscode.CompletionItemKind.Class, indentation)];
}

function trackBlockCompletionItems(context, indentation) {
  if (context.track === "CAMERA" && context.cameraCutBlock) {
    return [...optionItems(CAMERA_OPTIONS), ...trackEventItems(context.track, indentation), ...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword)];
  }
  return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...trackEventItems(context.track, indentation)];
}

function assetCompletionItems(first, previous, context, indentation) {
  if (["PROP", "PED", "VEHICLE"].includes(context.assetBlock) && !ASSET_COMMANDS.includes(first)) {
    if (previous === "PRESET") {
      return documentedItems(PRESETS, vscode.CompletionItemKind.EnumMember, "Animation preset", "Known cutscene animation metadata preset.");
    }
    if (MODEL_OPTIONS.includes(first)) {
      return modelPropertyArgumentItems(first, indentation);
    }
    return optionItems(MODEL_OPTIONS);
  }
  if (context.assetBlock === "LIGHT" && !ASSET_COMMANDS.includes(first)) {
    if (first === "TYPE" || previous === "TYPE") {
      return documentedItems(LIGHT_TYPES, vscode.CompletionItemKind.EnumMember, "Light type", "Cutscene light type.");
    }
    if (LIGHT_PROPERTIES.includes(first)) {
      return lightPropertyArgumentItems(first, indentation);
    }
    return optionItems(LIGHT_PROPERTIES);
  }
  if (["PROP", "PED", "VEHICLE"].includes(first)) {
    if (previous === "PRESET") {
      return documentedItems(PRESETS, vscode.CompletionItemKind.EnumMember, "Animation preset", "Known cutscene animation metadata preset.");
    }
    return [...optionItems(MODEL_OPTIONS), ...snippetsFromMap(ASSET_SNIPPETS, vscode.CompletionItemKind.Class, indentation)];
  }
  if (first === "LIGHT" || LIGHT_PROPERTIES.includes(first)) {
    if (first === "TYPE" || previous === "TYPE") {
      return documentedItems(LIGHT_TYPES, vscode.CompletionItemKind.EnumMember, "Light type", "Cutscene light type.");
    }
    return optionItems(LIGHT_PROPERTIES);
  }
  return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...snippetsFromMap(ASSET_SNIPPETS, vscode.CompletionItemKind.Class, indentation)];
}

function trackEventItems(track, indentation = "") {
  return snippetsFromMap(EVENT_SNIPPETS[track] || {}, vscode.CompletionItemKind.Function, indentation);
}

function eventCompletionItems(track, first, previous, context, indentation) {
  const assets = context.assets;
  if (isNumericToken(first)) {
    const valueItems = timelineValueItems(track, previous, context, indentation);
    if (valueItems) {
      return valueItems;
    }
  }
  if (first === "END") {
    return snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword);
  }
  if (previous === "TO") {
    return [snippet("attachment_name", "\"p_bone_name\"", vscode.CompletionItemKind.Value, "Attachment name", "Name/hash label used by the attachment event.")];
  }
  if (previous === "PRESET") {
    return documentedItems(PRESETS, vscode.CompletionItemKind.EnumMember, "Animation preset", "Known cutscene animation metadata preset.");
  }
  if (["VALUE", "COLOR", "FOR", "LANG", "LANGUAGE", "NEAR", "FAR", "MAP_LOD"].includes(previous)) {
    return [];
  }
  if (track === "CAMERA") {
    if (context.cameraCutBlock && !isNumericToken(first)) {
      return [...optionItems(CAMERA_OPTIONS), ...trackEventItems(track, indentation), ...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword)];
    }
    return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...assetItems(assets.camera), ...optionItems(CAMERA_OPTIONS), ...trackEventItems(track, indentation)];
  }
  if (track === "OBJECTS" || track === "ANIMATION" || track === "LOAD" || track === "CLEANUP") {
    return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...assetItems([...assets.prop, ...assets.ped, ...assets.vehicle]), ...trackEventItems(track, indentation)];
  }
  if (track === "LIGHTS") {
    return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...assetItems(assets.light), ...trackEventItems(track, indentation)];
  }
  if (track === "FADE") {
    return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...assetItems(assets.fade), ...optionItems(FADE_OPTIONS), ...trackEventItems(track, indentation)];
  }
  if (track === "OVERLAYS") {
    return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...assetItems(assets.overlay), ...trackEventItems(track, indentation)];
  }
  if (track === "SUBTITLES") {
    return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...optionItems(SUBTITLE_OPTIONS), ...trackEventItems(track, indentation)];
  }
  if (track === "AUDIO") {
    return [...snippetsFromMap(SECTION_END_SNIPPET, vscode.CompletionItemKind.Keyword), ...trackEventItems(track, indentation)];
  }
  if (!first) {
    return trackEventItems(track, indentation);
  }
  return [];
}

function timelineValueItems(track, previous, context, indentation) {
  const assets = context.assets;
  const modelAssets = [...assets.prop, ...assets.ped, ...assets.vehicle];
  if (track === "LOAD" || track === "CLEANUP") {
    switch (previous) {
      case "SCENE":
      case "UNLOAD_SCENE":
      case "ANIM_DICT":
      case "UNLOAD_ANIM_DICT":
      case "SUBTITLES":
      case "UNLOAD_SUBTITLES":
        return sceneNameItems(context, "Name inferred from CUTSCENE. Override manually if this asset uses a different name.", indentation);
      case "MODELS":
      case "UNLOAD_MODELS":
        return assetItems(modelAssets);
      case "LOAD_OVERLAYS":
      case "UNLOAD_OVERLAYS":
      case "LOAD":
      case "UNLOAD":
        return assetItems(assets.overlay);
      default:
        return null;
    }
  }
  if (track === "CAMERA" && (previous === "CUT" || previous === "DRAW_DISTANCE")) {
    return assetItems(assets.camera);
  }
  if ((track === "ANIMATION" || track === "OBJECTS") && ["PLAY", "STOP", "SHOW", "HIDE", "ATTACH"].includes(previous)) {
    return assetItems(modelAssets);
  }
  if (track === "LIGHTS" && ["ENABLE", "DISABLE", "ON", "OFF"].includes(previous)) {
    return assetItems(assets.light);
  }
  if (track === "FADE" && ["IN", "OUT", "FADE_IN", "FADE_OUT"].includes(previous)) {
    return assetItems(assets.fade);
  }
  if (track === "OVERLAYS" && ["LOAD", "UNLOAD", "SHOW", "HIDE"].includes(previous)) {
    return assetItems(assets.overlay);
  }
  if (track === "SUBTITLES" && previous === "SHOW") {
    return [snippet("subtitle key", "\"${1:SUB_KEY}\" FOR ${2:3.0}", vscode.CompletionItemKind.Snippet, "\"key\" FOR seconds", "Subtitle key and duration in seconds.", indentation)];
  }
  if (track === "AUDIO" && ["LOAD", "UNLOAD", "PLAY", "STOP"].includes(previous)) {
    return [snippet("name", "\"${1:name}\"", vscode.CompletionItemKind.Value, "\"name\"", "Audio bank or cue name.", indentation)];
  }
  return null;
}

function commandsForTrack(track) {
  switch (track) {
    case "LOAD":
      return ["SCENE", "MODELS", "UNLOAD_MODELS", "ANIM_DICT", "UNLOAD_ANIM_DICT", "SUBTITLES", "UNLOAD_SUBTITLES", "LOAD_OVERLAYS", "UNLOAD_OVERLAYS"];
    case "CAMERA":
      return ["CUT", "DRAW_DISTANCE"];
    case "ANIMATION":
      return ["PLAY", "STOP"];
    case "OBJECTS":
      return ["SHOW", "HIDE", "ATTACH"];
    case "FADE":
      return ["IN", "OUT", "FADE_IN", "FADE_OUT"];
    case "OVERLAYS":
      return ["LOAD", "UNLOAD", "SHOW", "HIDE"];
    case "LIGHTS":
      return ["ENABLE", "DISABLE", "ON", "OFF"];
    case "SUBTITLES":
      return ["SHOW", "HIDE"];
    case "AUDIO":
      return ["LOAD", "UNLOAD", "PLAY", "STOP"];
    case "CLEANUP":
      return ["UNLOAD_MODELS", "UNLOAD_ANIM_DICT", "UNLOAD_SUBTITLES", "UNLOAD_SCENE", "UNLOAD_OVERLAYS"];
    default:
      return [];
  }
}

function getDocumentContext(document, lineNumber) {
  let section = "ROOT";
  let track = null;
  let sceneName = null;
  let assetBlock = null;
  let cameraCutBlock = false;
  const assets = {
    camera: [],
    prop: [],
    ped: [],
    vehicle: [],
    light: [],
    fade: [],
    overlay: [],
  };

  for (let index = 0; index < lineNumber; index += 1) {
    const line = stripComment(document.lineAt(index).text).trim();
    if (!line) {
      continue;
    }
    const tokens = splitWords(line);
    if (!tokens.length) {
      continue;
    }
    const command = tokens[0].toUpperCase();
    if (section === "ROOT" && command === "CUTSCENE") {
      sceneName = tokens[1] || sceneName;
      continue;
    }
    if (command === "END") {
      section = "ROOT";
      track = null;
      assetBlock = null;
      cameraCutBlock = false;
      continue;
    }
    if (section === "ROOT" && command === "ASSETS") {
      section = "ASSETS";
      track = null;
      assetBlock = null;
      cameraCutBlock = false;
      continue;
    }
    if (section === "ROOT" && command === "TRACK") {
      section = "TRACK";
      track = (tokens[1] || "").toUpperCase();
      assetBlock = null;
      cameraCutBlock = false;
      continue;
    }
    if (section === "ASSETS") {
      if (ASSET_COMMANDS.includes(command)) {
        collectAsset(assets, command, tokens[1]);
        assetBlock = ["PROP", "PED", "VEHICLE", "LIGHT"].includes(command) ? command : null;
        continue;
      }
      if (assetBlock && (MODEL_OPTIONS.includes(command) || LIGHT_PROPERTIES.includes(command))) {
        continue;
      }
      assetBlock = null;
      continue;
    }
    if (section === "TRACK") {
      const isTimelineLine = isNumericToken(command);
      if (track === "CAMERA") {
        if (isTimelineLine) {
          cameraCutBlock = (tokens[1] || "").toUpperCase() === "CUT";
          continue;
        }
        if (cameraCutBlock && CAMERA_OPTIONS.includes(command)) {
          continue;
        }
        cameraCutBlock = false;
        continue;
      }
      if (isTimelineLine) {
        cameraCutBlock = false;
      }
    }
  }
  return { section, track, sceneName, assets, assetBlock, cameraCutBlock };
}

function collectAsset(assets, command, name) {
  if (!name) {
    return;
  }
  const clean = cleanName(name);
  const keyByCommand = {
    CAMERA: "camera",
    PROP: "prop",
    PED: "ped",
    VEHICLE: "vehicle",
    LIGHT: "light",
    FADE: "fade",
    OVERLAY: "overlay",
  };
  const key = keyByCommand[command];
  if (key && !assets[key].includes(clean)) {
    assets[key].push(clean);
  }
}

function cleanName(name) {
  return name.endsWith(":") ? name.slice(0, -1) : name;
}

function compileActiveCutScript(output) {
  const editor = vscode.window.activeTextEditor;
  if (!editor || editor.document.languageId !== "cutscript") {
    vscode.window.showErrorMessage("Open a .cuts or .cutscript file before compiling.");
    return;
  }
  const document = editor.document;
  if (document.isUntitled) {
    vscode.window.showErrorMessage("Save the CutScript file before compiling.");
    return;
  }

  document.save().then((saved) => {
    if (!saved) {
      vscode.window.showErrorMessage("Could not save the CutScript file.");
      return;
    }
    const pythonPath = vscode.workspace.getConfiguration("fivefuryCuts").get("pythonPath", "python");
    const scriptPath = document.uri.fsPath;
    const code = [
      "from pathlib import Path",
      "from fivefury import save_cutscript",
      "path = Path(__import__('sys').argv[1])",
      "output = save_cutscript(path)",
      "print(output)",
    ].join("; ");

    output.appendLine(`Compiling ${scriptPath}`);
    cp.execFile(pythonPath, ["-c", code, scriptPath], { cwd: path.dirname(scriptPath) }, (error, stdout, stderr) => {
      if (stdout.trim()) {
        output.appendLine(stdout.trim());
      }
      if (stderr.trim()) {
        output.appendLine(stderr.trim());
      }
      if (error) {
        output.show(true);
        vscode.window.showErrorMessage(`CutScript compile failed: ${error.message}`);
        return;
      }
      const generatedPath = stdout.trim().split(/\r?\n/).pop() || "output .cut";
      vscode.window.showInformationMessage(`CutScript compiled: ${generatedPath}`);
    });
  });
}

function items(labels, kind) {
  return labels.map((label) => {
    return completion(label, kind, label, undefined, undefined);
  });
}

function assetItems(labels) {
  return labels.map((label) => completion(label, vscode.CompletionItemKind.Reference, label, "Declared asset", "Asset declared earlier in the ASSETS block."));
}

function sceneNameItems(context, documentation, indentation) {
  const labels = context.sceneName ? [context.sceneName] : [];
  if (!labels.length) {
    return [snippet("scene name", "\"${1:scene_name}\"", vscode.CompletionItemKind.Value, "\"scene_name\"", documentation, indentation)];
  }
  return labels.map((label) => completion(label, vscode.CompletionItemKind.Value, `"${label}"`, "CUTSCENE name", documentation));
}

function documentedItems(labels, kind, detail, documentation) {
  return labels.map((label) => completion(label, kind, label, detail, documentation));
}

function optionItems(labels) {
  return labels.map((label) => completion(label, vscode.CompletionItemKind.Property, label, optionDetail(label), OPTION_DOCS[label] || "CutScript option."));
}

function flagItems() {
  return FLAGS.map((label) => {
    const documentation = label === "PLAYABLE"
      ? "Convenience preset: USE_ONE_AUDIO | IS_SECTIONED | USE_STORY_MODE | USE_IN_GAME_DOF_START | INTERNAL_CONCAT."
      : "CutSceneFlags enum value.";
    return completion(label, vscode.CompletionItemKind.EnumMember, label, "CutScene flag", documentation);
  });
}

function snippetsFromMap(definitions, kind) {
  return Object.entries(definitions).map(([label, definition]) => snippet(label, definition.insert, kind, definition.detail, definition.documentation));
}

function completion(label, kind, insertText, detail, documentation) {
  const item = new vscode.CompletionItem(label, kind);
  item.insertText = insertText;
  if (detail) {
    item.detail = detail;
  }
  if (documentation) {
    item.documentation = new vscode.MarkdownString(documentation);
  }
  return item;
}

function hover(title, documentation) {
  const markdown = new vscode.MarkdownString();
  markdown.appendCodeblock(title, "text");
  markdown.appendMarkdown(documentation);
  return new vscode.Hover(markdown);
}

function snippet(label, value, kind, detail, documentation) {
  const item = new vscode.CompletionItem(label, kind);
  item.insertText = new vscode.SnippetString(value);
  if (vscode.InsertTextMode && vscode.InsertTextMode.adjustIndentation !== undefined) {
    item.insertTextMode = vscode.InsertTextMode.adjustIndentation;
  }
  if (detail) {
    item.detail = detail;
  }
  if (documentation) {
    item.documentation = new vscode.MarkdownString(documentation);
  }
  return item;
}

function currentIndentation(_line) {
  return "";
}

function withoutLeadingTimeSnippet(value) {
  const withoutTime = value.replace(/^\$\{1:[^}]+\}\s+/, "");
  return withoutTime.replace(/\$\{(\d+)(:[^}]*)?\}/g, (_match, index, placeholder) => {
    return `\${${Number(index) - 1}${placeholder || ""}}`;
  });
}

function isNumericToken(value) {
  return /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[-+]?\d+)?$/i.test(value);
}

function optionDetail(label) {
  switch (label) {
    case "POS":
    case "POSITION":
      return `${label} x y z`;
    case "ROT":
    case "ROTATION":
      return `${label} pitch yaw roll`;
    case "COLOR":
    case "COLOUR":
      return `${label} r g b`;
    case "CORONA":
      return "CORONA size intensity";
    default:
      return label;
  }
}

function trackDocumentation(name) {
  switch (name) {
    case "LOAD":
      return "Load/unload scenes, models, animation dictionaries, subtitles and overlays.";
    case "CAMERA":
      return "Camera cuts and camera-specific settings. ROT uses Euler XYZ degrees.";
    case "ANIMATION":
      return "Object animation binding. PLAY targets an object, not a literal clip name.";
    case "OBJECTS":
      return "Show/hide scene objects and set simple attachments.";
    case "FADE":
      return "Screen fade in/out events.";
    case "OVERLAYS":
      return "Overlay load/show/hide/unload events.";
    case "LIGHTS":
      return "Enable or disable declared cutscene lights.";
    case "SUBTITLES":
      return "Show/hide subtitle keys.";
    case "AUDIO":
      return "Load, unload, play and stop audio cue names.";
    case "CLEANUP":
      return "Convenience unload events near the end of the timeline.";
    default:
      return "CutScript timeline track.";
  }
}

function stripComment(line) {
  let quote = null;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (quote) {
      if (char === quote && line[index - 1] !== "\\") {
        quote = null;
      }
      continue;
    }
    if (char === "\"" || char === "'") {
      quote = char;
      continue;
    }
    if ((char === "#" && !looksLikeCssHexColor(line.slice(index))) || char === ";") {
      return line.slice(0, index);
    }
    if (char === "/" && line[index + 1] === "/") {
      return line.slice(0, index);
    }
  }
  return line;
}

function looksLikeCssHexColor(value) {
  const match = value.match(/^#([0-9A-Fa-f]{3}|[0-9A-Fa-f]{4}|[0-9A-Fa-f]{6}|[0-9A-Fa-f]{8})\b/);
  return Boolean(match);
}

function splitWords(line) {
  const matches = line.match(/"[^"]*"|'[^']*'|\S+/g);
  if (!matches) {
    return [];
  }
  return matches.map((token) => token.replace(/^["']|["']$/g, ""));
}

module.exports = {
  activate,
  deactivate,
};
