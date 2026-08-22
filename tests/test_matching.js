const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const INDEX_PATH = path.join(__dirname, '..', 'index.html');

function makeElement() {
    return {
        value: '',
        files: [],
        textContent: '',
        innerHTML: '',
        disabled: false,
        classList: { add() {}, remove() {}, toggle() {} },
        addEventListener() {},
        appendChild() {},
        scrollIntoView() {},
    };
}

function loadMatchingApp() {
    const html = fs.readFileSync(INDEX_PATH, 'utf8');
    const scriptMatch = html.match(/<script>([\s\S]*)<\/script>/);
    assert.ok(scriptMatch, 'index.html must contain the application script');

    const elements = new Map();
    const document = {
        head: makeElement(),
        createElement: makeElement,
        getElementById(id) {
            if (!elements.has(id)) elements.set(id, makeElement());
            return elements.get(id);
        },
    };
    const sandbox = {
        alert() {},
        console,
        document,
        fetch: async () => ({ json: async () => ({}) }),
        File: function File() {},
        FormData: function FormData() { this.append = () => {}; },
        Image: function Image() {},
        Promise,
        URL: { createObjectURL: () => 'blob:test', revokeObjectURL() {} },
        window: {},
    };
    vm.createContext(sandbox);
    vm.runInContext(`${scriptMatch[1]}
        globalThis.__matchingTestApi = {
            normalizeKey,
            parseCabinParts,
            compareNames,
            setData(people, ocr) {
                pobData = { marine: people, catering: [], passenger: [] };
                ocrResults = ocr;
            },
            match(scanContext) {
                matchAll(scanContext);
                return JSON.parse(JSON.stringify(pobData.marine));
            },
            effectiveStatus(person) { return effectiveStatus(person); },
            diagnostics() {
                return typeof matchingDiagnostics === 'undefined'
                    ? null
                    : JSON.parse(JSON.stringify(matchingDiagnostics));
            },
        };
    `, sandbox);
    return sandbox.__matchingTestApi;
}

function person(cabinBed, name) {
    const bed = cabinBed.slice(-1);
    return {
        cabin: cabinBed.slice(0, -1),
        bed,
        cabinBed,
        name,
        matchStatus: 'absent',
        userOverride: null,
        sourceFile: null,
        reviewReason: null,
        ocrCabin: null,
        ocrName: null,
    };
}

function tag(cabinBed, name, sourceFile = 'board.jpg') {
    return {
        cabin_bed: cabinBed,
        name_tag: name,
        sourceFile,
        raw: `${cabinBed}|${name}`,
    };
}

test('current: cabin normalization removes spaces and hyphens', () => {
    const app = loadMatchingApp();
    assert.equal(app.normalizeKey(' b-401 a '), 'B401A');
    assert.deepEqual(
        JSON.parse(JSON.stringify(app.parseCabinParts('B-401A'))),
        { base: 'B401', bed: 'A', full: 'B401A' },
    );
});

test('regression: first-name prefix with a different surname is weak evidence', () => {
    const app = loadMatchingApp();
    assert.equal(app.compareNames('SOMCHAI PRASERT', 'SOM SIRIPORN'), 'weak');
});

test('current: exact cabin and exact name is ok', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'AKARANET SIRIPORN')]);
    assert.equal(app.match()[0].matchStatus, 'ok');
});

test('current: exact cabin and abbreviated surname is ok', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'AKARANET SI')]);
    assert.equal(app.match()[0].matchStatus, 'ok');
});

test('regression: weak first-name prefix at the expected cabin requires review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'SOMCHAI PRASERT')], [tag('B-401A', 'SOM SIRIPORN')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'location_name_conflict');
});

test('regression: a different person at the expected cabin requires review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'NATTAWUT YINDEE')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'location_name_conflict');
});

test('current: correct person in another bed is review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401B', 'AKARANET SI')]);
    assert.equal(app.match()[0].matchStatus, 'review');
});

test('regression: one OCR tag cannot satisfy duplicate POB rows', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN'), person('B401A', 'AKARANET SIRIPORN')],
        [tag('B-401A', 'AKARANET SI')],
    );
    const results = app.match();
    assert.deepEqual(Array.from(results, (item) => item.matchStatus), ['review', 'review']);
    assert.ok(results.every((item) => item.matchReasonCode === 'duplicate_pob_record'));
});

test('current: manual override replaces only the effective status', () => {
    const app = loadMatchingApp();
    const computed = { matchStatus: 'review', userOverride: null };
    assert.equal(app.effectiveStatus(computed), 'review');
    computed.userOverride = 'ok';
    assert.equal(app.effectiveStatus(computed), 'ok');
    assert.equal(computed.matchStatus, 'review');
});

test('target: unique exact cabin and exact name records its reason', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'AKARANET SIRIPORN')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'ok');
    assert.equal(result.matchReasonCode, 'exact_location_exact_name');
    assert.ok(result.assignedOcrId);
});

test('target: unique two-letter surname abbreviation is ok only at exact cabin and bed', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'AKARANET SI')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'ok');
    assert.equal(result.matchReasonCode, 'exact_location_abbreviated_name');
});

test('target: competing POB surname candidates prevent abbreviation from becoming ok', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN'), person('B401A', 'AKARANET SIRICHAI')],
        [tag('B-401A', 'AKARANET SI')],
    );
    const results = app.match();
    assert.deepEqual(Array.from(results, (item) => item.matchStatus), ['review', 'review']);
    assert.ok(results.every((item) => item.matchReasonCode === 'ambiguous_pob_candidates'));
    assert.ok(results.every((item) => item.assignedOcrId === null));
});

test('target: identical duplicate POB rows use duplicate_pob_record and are not assigned', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN'), person('B401A', 'AKARANET SIRIPORN')],
        [tag('B-401A', 'AKARANET SI')],
    );
    const results = app.match();
    assert.deepEqual(Array.from(results, (item) => item.matchStatus), ['review', 'review']);
    assert.ok(results.every((item) => item.matchReasonCode === 'duplicate_pob_record'));
    assert.ok(results.every((item) => item.assignedOcrId === null));
});

test('target: a different detected person at the expected location is review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'NATTAWUT YINDEE')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'location_name_conflict');
    assert.equal(result.assignedOcrId, null);
});

test('target: a unique correct person in the wrong bed is assigned for review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401B', 'AKARANET SI')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'wrong_bed');
    assert.ok(result.assignedOcrId);
});

test('target: a unique correct person in the wrong cabin is assigned for review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('C-501A', 'AKARANET SI')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'wrong_cabin');
    assert.ok(result.assignedOcrId);
});

test('target: one OCR tag cannot satisfy two distinct POB rows', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN'), person('B402A', 'AKARANET SIRIPORN')],
        [tag('B-401A', 'AKARANET SI')],
    );
    const results = app.match();
    assert.equal(results.filter((item) => item.matchStatus === 'ok').length, 1);
    assert.equal(results.filter((item) => item.assignedOcrId).length, 1);
});

test('target: duplicate identical OCR tags become one logical tag with all sources', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN')],
        [tag('B-401A', 'AKARANET SI', 'board-1.jpg'), tag('B-401A', 'AKARANET SI', 'board-2.jpg')],
    );
    const result = app.match()[0];
    const diagnostics = app.diagnostics();
    assert.equal(result.matchStatus, 'ok');
    assert.equal(result.matchEvidence.duplicateCount, 2);
    assert.deepEqual(Array.from(result.matchEvidence.sourceFiles), ['board-1.jpg', 'board-2.jpg']);
    assert.equal(diagnostics.logicalOcrCount, 1);
});

test('target: duplicate OCR names at distinct exact locations stay independently assignable', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN'), person('B402A', 'AKARANET SIRIPORN')],
        [tag('B-401A', 'AKARANET SI'), tag('B-402A', 'AKARANET SI')],
    );
    const results = app.match();
    assert.deepEqual(Array.from(results, (item) => item.matchStatus), ['ok', 'ok']);
    assert.equal(new Set(results.map((item) => item.assignedOcrId)).size, 2);
});

test('target: one-edit typo at exact location can only produce review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'AKARANETT SI')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'conservative_name_typo');
    assert.ok(result.assignedOcrId);
});

test('target: typo evidence in a wrong cabin is not automatically assigned', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('C-501A', 'AKARANETT SI')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'absent');
    assert.equal(result.assignedOcrId, null);
});

test('target: conflicting exact-name and typo-at-location evidence is review without assignment', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN')],
        [tag('B-401A', 'AKARANETT SI'), tag('B-402A', 'AKARANET SIRIPORN')],
    );
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'conflicting_evidence');
    assert.equal(result.assignedOcrId, null);
});

test('target: different OCR identities at one location are conflicting evidence', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN')],
        [tag('B-401A', 'AKARANET SI'), tag('B-401A', 'NATTAWUT YINDEE')],
    );
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'conflicting_evidence');
    assert.equal(result.assignedOcrId, null);
});

test('target: equal wrong-location candidates are review without assignment', () => {
    const app = loadMatchingApp();
    app.setData(
        [person('B401A', 'AKARANET SIRIPORN')],
        [tag('B-402A', 'AKARANET SI'), tag('B-403A', 'AKARANET SI')],
    );
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'ambiguous_ocr_candidates');
    assert.equal(result.assignedOcrId, null);
});

test('target: weak first-name prefix at the expected location is review, never ok', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'SOMCHAI PRASERT')], [tag('B-401A', 'SOM SIRIPORN')]);
    const result = app.match()[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'location_name_conflict');
});

test('target: missing tag after successful OCR is absent', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], []);
    const result = app.match({ totalImages: 1, successfulImages: 1, failedImages: 0 })[0];
    assert.equal(result.matchStatus, 'absent');
    assert.equal(result.matchReasonCode, 'no_ocr_match');
});

test('target: failed OCR makes an otherwise missing tag review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], []);
    const result = app.match({ totalImages: 1, successfulImages: 0, failedImages: 1 })[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'ocr_unavailable');
});

test('target: partial OCR failure makes an otherwise missing tag review', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], []);
    const result = app.match({ totalImages: 2, successfulImages: 1, failedImages: 1 })[0];
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'partial_ocr_failure');
});

test('target: extra OCR tags remain visible as unassigned evidence', () => {
    const app = loadMatchingApp();
    app.setData([], [tag('B-401A', 'EXTRA PERSON')]);
    app.match();
    const diagnostics = app.diagnostics();
    assert.equal(diagnostics.unassignedOcr.length, 1);
    assert.equal(diagnostics.unassignedOcr[0].name, 'EXTRA PERSON');
});

test('target: manual override preserves the computed matching reason', () => {
    const app = loadMatchingApp();
    app.setData([person('B401A', 'AKARANET SIRIPORN')], [tag('B-401A', 'NATTAWUT YINDEE')]);
    const result = app.match()[0];
    assert.equal(result.matchReasonCode, 'location_name_conflict');
    result.userOverride = 'ok';
    assert.equal(app.effectiveStatus(result), 'ok');
    assert.equal(result.matchStatus, 'review');
    assert.equal(result.matchReasonCode, 'location_name_conflict');
});
