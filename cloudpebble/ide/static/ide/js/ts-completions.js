/*
 * TypeScript Completions Bridge
 *
 * Manages a Web Worker running the TypeScript language service and provides
 * CodeMirror 4 compatible hint functions for Alloy (JavaScript) projects.
 */

CloudPebble.TSCompletions = new (function() {
    var self = this;
    var Pos = CodeMirror.Pos;
    var worker = null;
    var messageId = 0;
    var callbacks = {};
    var mReady = false;
    var mInitialising = false;
    var mFailed = false;
    var readyCallbacks = [];

    function send(msg, callback) {
        var id = ++messageId;
        msg._id = id;
        if (callback) callbacks[id] = callback;
        worker.postMessage(msg);
    }

    function onMessage(e) {
        var data = e.data;
        if (data.command === 'ready') {
            mReady = true;
            mInitialising = false;
            for (var i = 0; i < readyCallbacks.length; i++) {
                readyCallbacks[i]();
            }
            readyCallbacks = [];
            return;
        }
        if (data._id && callbacks[data._id]) {
            callbacks[data._id](data.result);
            delete callbacks[data._id];
        }
    }

    function whenReady(fn) {
        if (mReady) {
            fn();
        } else {
            readyCallbacks.push(fn);
        }
    }

    /**
     * Initialize the TypeScript worker. Call once when an Alloy project is loaded.
     * The typingsUrl should point to the alloy-typings.json bundle.
     */
    this.init = function(typingsUrl, toolchainTypingsUrl) {
        if (mInitialising || mReady) return;
        if (!typingsUrl) return;
        mInitialising = true;
        mFailed = false;

        // Resolve the worker script URL relative to the typings URL. The
        // version query rides along from the typings URL where present: the
        // worker is fetched by XHR, so without one a returning browser keeps
        // serving the old language service after a deploy.
        var version = (typingsUrl.split('?')[1] || '');
        var workerScriptUrl = typingsUrl.split('?')[0].replace('ts-typings/alloy-typings.json', 'js/ts-worker.js')
            + (version ? '?' + version : '');

        // Fetch the worker script asynchronously, then create a blob Worker
        var xhr = new XMLHttpRequest();
        xhr.open('GET', workerScriptUrl);
        xhr.onload = function() {
            if (xhr.status !== 200) {
                console.warn('TS Completions: could not load worker script (' + xhr.status + ')');
                mFailed = true;
                mInitialising = false;
                return;
            }
            try {
                var absTypingsUrl = new URL(typingsUrl, window.location.href).href;
                var absToolchainUrl = toolchainTypingsUrl
                    ? new URL(toolchainTypingsUrl, window.location.href).href
                    : '';
                var workerCode = xhr.responseText + '\ninit(' + JSON.stringify(absTypingsUrl)
                    + ', ' + JSON.stringify(absToolchainUrl) + ');';
                var blob = new Blob([workerCode], {type: 'application/javascript'});
                var blobUrl = URL.createObjectURL(blob);

                worker = new Worker(blobUrl);
                worker.onmessage = onMessage;
                worker.onerror = function(e) {
                    console.error('TS Worker error:', e);
                    mFailed = true;
                    mInitialising = false;
                };
            } catch (e) {
                console.error('Failed to init TS completions:', e);
                mFailed = true;
                mInitialising = false;
            }
        };
        xhr.onerror = function() {
            console.warn('TS Completions: network error loading worker script');
            mFailed = true;
            mInitialising = false;
        };
        xhr.send();
    };

    /**
     * Update a file's content in the TypeScript virtual filesystem.
     */
    this.updateFile = function(path, content) {
        if (!worker || mFailed) return;
        send({command: 'updateFile', file: path, content: content});
    };

    /**
     * Remove a file from the TypeScript virtual filesystem.
     */
    this.removeFile = function(path) {
        if (!worker || mFailed) return;
        send({command: 'removeFile', file: path});
    };

    /**
     * Check if the TS completion system is available.
     */
    this.isAvailable = function() {
        return !mFailed && (mReady || mInitialising);
    };

    // Kind -> CSS class mapping for completion icons
    var kindClasses = {
        'keyword': 'ts-kind-keyword',
        'function': 'ts-kind-function',
        'method': 'ts-kind-function',
        'property': 'ts-kind-property',
        'variable': 'ts-kind-variable',
        'let': 'ts-kind-variable',
        'const': 'ts-kind-variable',
        'local variable': 'ts-kind-variable',
        'class': 'ts-kind-class',
        'interface': 'ts-kind-class',
        'type': 'ts-kind-class',
        'enum': 'ts-kind-class',
        'module': 'ts-kind-module',
        'string': 'ts-kind-string'
    };

    /**
     * CodeMirror 4 async hint function for JavaScript files.
     * Drop-in replacement for CloudPebble.Editor.Autocomplete.complete
     */
    this.complete = function(editor, finishCompletion, options) {
        if (mFailed || !worker) return;

        var cursor = editor.getCursor();
        var token = editor.getTokenAt(cursor);

        // Don't autocomplete on empty tokens or very short ones
        if (!token || (token.string.replace(/[^a-z0-9_$.]/gi, '').length < 1
                && token.string !== '.')) {
            return;
        }

        var filePath = editor.file_path || '/src/main.js';
        var content = editor.getValue();
        var position = editor.indexFromPos(cursor);

        // Make sure the worker has the latest content
        send({command: 'updateFile', file: filePath, content: content});

        whenReady(function() {
            send({
                command: 'getCompletions',
                file: filePath,
                position: position
            }, function(result) {
                if (!result || !result.completions || result.completions.length === 0) {
                    return;
                }

                var completions = [];
                for (var i = 0; i < result.completions.length; i++) {
                    var c = result.completions[i];
                    completions.push({
                        text: c.name,
                        displayText: c.name,
                        className: kindClasses[c.kind] || 'ts-kind-other',
                        render: renderCompletion
                    });
                }

                // Figure out the replacement range
                var from, to;
                if (token.string === '.') {
                    from = to = cursor;
                } else {
                    from = Pos(cursor.line, token.start);
                    to = Pos(cursor.line, token.end);
                }

                var result = {
                    list: completions,
                    from: from,
                    to: to
                };

                finishCompletion(result);
            });
        });
    };
    this.complete.async = true;

    function renderCompletion(elt, data, completion) {
        var icon = document.createElement('span');
        icon.className = 'ts-completion-icon ' + (completion.className || '');
        icon.textContent = getKindChar(completion.className);
        elt.appendChild(icon);

        var text = document.createElement('span');
        text.className = 'ts-completion-text';
        text.textContent = completion.displayText || completion.text;
        elt.appendChild(text);
    }

    function getKindChar(className) {
        if (!className) return '?';
        if (className.indexOf('function') >= 0) return 'f';
        if (className.indexOf('property') >= 0) return 'p';
        if (className.indexOf('variable') >= 0) return 'v';
        if (className.indexOf('class') >= 0) return 'C';
        if (className.indexOf('module') >= 0) return 'M';
        if (className.indexOf('keyword') >= 0) return 'k';
        if (className.indexOf('string') >= 0) return 's';
        return '\u00B7';
    }

    /**
     * Get diagnostics for a JavaScript file. Returns via callback.
     */
    this.getErrors = function(filePath, content, callback) {
        if (mFailed || !worker) {
            callback({errors: []});
            return;
        }
        send({command: 'updateFile', file: filePath, content: content});
        whenReady(function() {
            send({command: 'getErrors', file: filePath}, callback);
        });
    };
})();
