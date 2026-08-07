/*
 * TypeScript Language Service Web Worker
 *
 * Runs the TypeScript compiler + language service in a Web Worker to provide
 * code completions, diagnostics, and type info for Alloy (JavaScript) projects.
 * Uses Moddable's .d.ts type definitions for Pebble/Alloy APIs.
 */

/* global ts, importScripts */

var TS_CDN = 'https://cdn.jsdelivr.net/npm/typescript@5.9/lib/typescript.min.js';

var files = {};       // path -> {content, version}
var typings = {};     // path -> content (from alloy-typings.json)
var service = null;
var ready = false;
var pendingMessages = [];

// Load TypeScript
importScripts(TS_CDN);

self.onmessage = function(e) {
    if (!ready) {
        pendingMessages.push(e);
        return;
    }
    handleMessage(e.data);
};

function handleMessage(msg) {
    var result;
    try {
        switch (msg.command) {
            case 'getCompletions':
                result = getCompletions(msg.file, msg.position);
                break;
            case 'getErrors':
                result = getErrors(msg.file);
                break;
            case 'getQuickInfo':
                result = getQuickInfo(msg.file, msg.position);
                break;
            case 'updateFile':
                updateFile(msg.file, msg.content);
                result = {ok: true};
                break;
            case 'removeFile':
                removeFile(msg.file);
                result = {ok: true};
                break;
            default:
                result = {error: 'unknown command: ' + msg.command};
        }
    } catch (err) {
        result = {error: err.message || String(err)};
    }
    self.postMessage({_id: msg._id, result: result});
}

function init(typingsUrl) {
    // Fetch the alloy typings bundle
    var xhr = new XMLHttpRequest();
    xhr.open('GET', typingsUrl, false); // synchronous in worker
    xhr.send();
    if (xhr.status === 200) {
        typings = JSON.parse(xhr.responseText);
    }

    // Create the language service
    service = ts.createLanguageService(createHost());

    ready = true;

    // Process any messages that arrived before init completed
    for (var i = 0; i < pendingMessages.length; i++) {
        handleMessage(pendingMessages[i].data);
    }
    pendingMessages = [];

    self.postMessage({command: 'ready'});
}

function createHost() {
    return {
        getScriptFileNames: function() {
            var names = Object.keys(files);
            // Add typings as ambient declarations
            var typingPaths = Object.keys(typings);
            for (var i = 0; i < typingPaths.length; i++) {
                names.push('/typings/' + typingPaths[i]);
            }
            return names;
        },
        getScriptVersion: function(path) {
            if (files[path]) return String(files[path].version);
            return '1'; // typings don't change
        },
        getScriptSnapshot: function(path) {
            var content;
            if (files[path]) {
                content = files[path].content;
            } else if (path.indexOf('/typings/') === 0) {
                var typingKey = path.substring('/typings/'.length);
                content = typings[typingKey];
            } else if (path === getDefaultLibPath()) {
                // Return a minimal lib for ES2025 basics
                content = getDefaultLib();
            }
            if (content === undefined) return undefined;
            return ts.ScriptSnapshot.fromString(content);
        },
        getCurrentDirectory: function() { return '/'; },
        getCompilationSettings: function() {
            return {
                target: ts.ScriptTarget.ES2022,
                module: ts.ModuleKind.ES2022,
                moduleResolution: ts.ModuleResolutionKind.Bundler,
                allowJs: true,
                checkJs: true,
                // .tsx sources: without these the service reports every JSX
                // element as a syntax error. The import source matches the
                // tsconfig the build generates, so completions and diagnostics
                // agree with what the compiler will actually do.
                jsx: ts.JsxEmit.ReactJSX,
                jsxImportSource: 'runtime',
                strict: false,
                noEmit: true,
                esModuleInterop: true,
                skipLibCheck: true,
                baseUrl: '/',
                paths: {
                    'commodetto/*': ['/typings/commodetto/*'],
                    'piu/*': ['/typings/piu/*'],
                    'pebble/*': ['/typings/pebble/*'],
                    'Resource': ['/typings/Resource.d.ts'],
                    'embedded:sensor/*': ['/typings/embedded/*'],
                    'embedded:network/*': ['/typings/embedded_network/*'],
                }
            };
        },
        getDefaultLibFileName: function() { return getDefaultLibPath(); },
        fileExists: function(path) {
            if (files[path]) return true;
            if (path === getDefaultLibPath()) return true;
            if (path.indexOf('/typings/') === 0) {
                var key = path.substring('/typings/'.length);
                return typings[key] !== undefined;
            }
            return false;
        },
        readFile: function(path) {
            if (files[path]) return files[path].content;
            if (path.indexOf('/typings/') === 0) {
                var key = path.substring('/typings/'.length);
                return typings[key];
            }
            if (path === getDefaultLibPath()) return getDefaultLib();
            return undefined;
        },
        directoryExists: function(path) {
            // Check if any file starts with this path
            var allPaths = Object.keys(files).concat(
                Object.keys(typings).map(function(k) { return '/typings/' + k; })
            );
            for (var i = 0; i < allPaths.length; i++) {
                if (allPaths[i].indexOf(path) === 0) return true;
            }
            return false;
        },
        getDirectories: function() { return []; }
    };
}

var _defaultLibPath = '/lib.es2022.d.ts';
function getDefaultLibPath() { return _defaultLibPath; }

var _defaultLib = null;
function getDefaultLib() {
    if (_defaultLib !== null) return _defaultLib;
    // Fetch the default lib from CDN
    var xhr = new XMLHttpRequest();
    xhr.open('GET', 'https://cdn.jsdelivr.net/npm/typescript@5.9/lib/lib.es2022.full.d.ts', false);
    xhr.send();
    if (xhr.status === 200) {
        _defaultLib = xhr.responseText;
    } else {
        // Minimal fallback
        _defaultLib = [
            'interface Array<T> { length: number; push(...items: T[]): number; pop(): T | undefined; map<U>(fn: (v: T) => U): U[]; filter(fn: (v: T) => boolean): T[]; forEach(fn: (v: T) => void): void; indexOf(item: T): number; slice(start?: number, end?: number): T[]; splice(start: number, deleteCount?: number, ...items: T[]): T[]; join(sep?: string): string; }',
            'interface String { length: number; charAt(i: number): string; indexOf(s: string): number; slice(start?: number, end?: number): string; split(sep: string): string[]; trim(): string; replace(pattern: string | RegExp, replacement: string): string; startsWith(s: string): boolean; endsWith(s: string): boolean; includes(s: string): boolean; toLowerCase(): string; toUpperCase(): string; substring(start: number, end?: number): string; }',
            'interface Number { toFixed(digits?: number): string; toString(radix?: number): string; }',
            'interface Boolean {}',
            'interface Object { hasOwnProperty(key: string): boolean; }',
            'interface Function { call(thisArg: any, ...args: any[]): any; apply(thisArg: any, args?: any[]): any; bind(thisArg: any, ...args: any[]): Function; }',
            'interface RegExp { test(s: string): boolean; exec(s: string): RegExpExecArray | null; }',
            'interface RegExpExecArray extends Array<string> { index: number; input: string; }',
            'interface Date { getTime(): number; getFullYear(): number; getMonth(): number; getDate(): number; getDay(): number; getHours(): number; getMinutes(): number; getSeconds(): number; getMilliseconds(): number; toISOString(): string; toLocaleDateString(): string; toLocaleTimeString(): string; }',
            'interface DateConstructor { new(): Date; new(value: number | string): Date; new(year: number, month: number, date?: number, hours?: number, minutes?: number, seconds?: number, ms?: number): Date; now(): number; parse(s: string): number; }',
            'declare var Date: DateConstructor;',
            'interface Math { PI: number; abs(x: number): number; ceil(x: number): number; floor(x: number): number; max(...values: number[]): number; min(...values: number[]): number; pow(x: number, y: number): number; random(): number; round(x: number): number; sin(x: number): number; cos(x: number): number; sqrt(x: number): number; }',
            'declare var Math: Math;',
            'interface JSON { parse(text: string): any; stringify(value: any, replacer?: any, space?: number): string; }',
            'declare var JSON: JSON;',
            'interface Promise<T> { then<R>(onFulfilled: (value: T) => R): Promise<R>; catch(onRejected: (reason: any) => any): Promise<any>; finally(onFinally: () => void): Promise<T>; }',
            'interface PromiseConstructor { new<T>(executor: (resolve: (value: T) => void, reject: (reason?: any) => void) => void): Promise<T>; resolve<T>(value: T): Promise<T>; reject(reason?: any): Promise<never>; all<T>(values: Promise<T>[]): Promise<T[]>; }',
            'declare var Promise: PromiseConstructor;',
            'interface ArrayBuffer { readonly byteLength: number; slice(begin: number, end?: number): ArrayBuffer; }',
            'interface ArrayBufferConstructor { new(byteLength: number): ArrayBuffer; }',
            'declare var ArrayBuffer: ArrayBufferConstructor;',
            'interface Uint8Array { readonly length: number; readonly byteLength: number; readonly buffer: ArrayBuffer; [index: number]: number; }',
            'interface Uint8ArrayConstructor { new(length: number): Uint8Array; new(buffer: ArrayBuffer): Uint8Array; }',
            'declare var Uint8Array: Uint8ArrayConstructor;',
            'interface Int32Array { readonly length: number; [index: number]: number; }',
            'interface Map<K, V> { get(key: K): V | undefined; set(key: K, value: V): this; has(key: K): boolean; delete(key: K): boolean; readonly size: number; forEach(fn: (value: V, key: K) => void): void; }',
            'interface MapConstructor { new<K, V>(): Map<K, V>; }',
            'declare var Map: MapConstructor;',
            'interface Set<T> { add(value: T): this; has(value: T): boolean; delete(value: T): boolean; readonly size: number; }',
            'interface SetConstructor { new<T>(): Set<T>; }',
            'declare var Set: SetConstructor;',
            'declare function parseInt(s: string, radix?: number): number;',
            'declare function parseFloat(s: string): number;',
            'declare function isNaN(value: any): boolean;',
            'declare function isFinite(value: any): boolean;',
            'declare var NaN: number;',
            'declare var Infinity: number;',
            'declare var undefined: undefined;',
            'interface Error { message: string; name: string; stack?: string; }',
            'interface ErrorConstructor { new(message?: string): Error; }',
            'declare var Error: ErrorConstructor;',
            'declare function trace(msg: string): void;',
        ].join('\n');
    }
    return _defaultLib;
}

function updateFile(path, content) {
    if (files[path]) {
        files[path].content = content;
        files[path].version++;
    } else {
        files[path] = {content: content, version: 1};
    }
}

function removeFile(path) {
    delete files[path];
}

function getCompletions(filePath, position) {
    if (!service) return {completions: []};

    var info = service.getCompletionsAtPosition(filePath, position, {
        includeCompletionsForModuleExports: true,
        includeCompletionsWithInsertText: true
    });

    if (!info) return {completions: []};

    var completions = [];
    var items = info.entries;
    for (var i = 0; i < items.length && completions.length < 50; i++) {
        var entry = items[i];
        // Skip internal/private completions
        if (entry.name.charAt(0) === '_' && entry.name.charAt(1) === '_') continue;

        completions.push({
            name: entry.name,
            kind: entry.kind,
            sortText: entry.sortText
        });
    }

    return {completions: completions};
}

function getErrors(filePath) {
    if (!service) return {errors: []};

    var syntactic = service.getSyntacticDiagnostics(filePath);
    var semantic = service.getSemanticDiagnostics(filePath);
    var all = syntactic.concat(semantic);

    var errors = [];
    for (var i = 0; i < all.length && errors.length < 50; i++) {
        var d = all[i];
        if (d.file) {
            var pos = d.file.getLineAndCharacterOfPosition(d.start);
            errors.push({
                line: pos.line,
                ch: pos.character,
                message: ts.flattenDiagnosticMessageText(d.messageText, '\n'),
                severity: d.category // 0=warning, 1=error, 2=suggestion, 3=message
            });
        }
    }

    return {errors: errors};
}

function getQuickInfo(filePath, position) {
    if (!service) return null;

    var info = service.getQuickInfoAtPosition(filePath, position);
    if (!info) return null;

    return {
        text: ts.displayPartsToString(info.displayParts),
        documentation: ts.displayPartsToString(info.documentation || [])
    };
}

// init() is called by the bridge after injecting the typings URL into the blob.
