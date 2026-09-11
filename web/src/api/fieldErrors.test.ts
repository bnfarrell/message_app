import { describe, expect, it } from 'vitest'
import { ApiError } from './client'
import { fieldErrors } from './fieldErrors'

function failure(details: unknown, message = 'Invalid request body'): ApiError {
  return new ApiError(400, 'VALIDATION_FAILED', message, details)
}

describe('fieldErrors', () => {
  describe('the object shape — domain validators and patch_changes', () => {
    it('keys the copy by the camelCase field the server named', () => {
      expect(fieldErrors(failure({ escalationMinutes: 'required' }))).toEqual({
        escalationMinutes: 'This field is required.',
      })
    })

    it('carries every field in one failure', () => {
      // update_settings can refuse several cleared fields at once.
      expect(fieldErrors(failure({ name: 'required', currency: 'required' }))).toEqual({
        name: 'This field is required.',
        currency: 'This field is required.',
      })
    })

    it('stringifies a non-string value rather than rendering [object Object]', () => {
      expect(fieldErrors(failure({ slaMinutes: 0 }))).toEqual({ slaMinutes: '0' })
    })
  })

  describe('reason codes become copy (D93)', () => {
    // Every code server/app/ raises today. Grepped, not guessed: `details={` outside
    // `e.errors(...)` appears in _patch.py, guests.py and properties.py and nowhere else.
    const SERVER_CODES = ['required', 'invalid_phone_number', 'invalid_timezone']

    it.each(SERVER_CODES)('words %s as a sentence rather than leaving the code on screen', (code) => {
      const shown = fieldErrors(failure({ smsNumber: code })).smsNumber!
      expect(shown).not.toBe(code)
      expect(shown).not.toMatch(/_/) // no snake_case survivor
      expect(shown).toMatch(/^[A-Z].*\.$/) // a capitalised sentence, ending in a full stop
    })

    it('names the phone format instead of saying invalid_phone_number under a Phone box', () => {
      expect(fieldErrors(failure({ phone: 'invalid_phone_number' }))).toEqual({
        phone: 'Enter a valid phone number, for example +1 555 012 3456.',
      })
    })

    it('says what a time zone has to be', () => {
      expect(fieldErrors(failure({ timezone: 'invalid_timezone' }))).toEqual({
        timezone: 'Not a recognised IANA time zone.',
      })
    })

    it('passes an unknown code through verbatim rather than swallowing it', () => {
      // A code this map has not caught up with must still reach the admin: ugly beats absent,
      // and a generic apology would hide that the server said something specific.
      expect(fieldErrors(failure({ brand: 'not_a_code_we_know' }))).toEqual({
        brand: 'not_a_code_we_know',
      })
    })

    it('leaves the array shape alone — msg is already a sentence', () => {
      // The map is keyed on codes; a Pydantic msg that happened to collide would still be wrong
      // to rewrite, so the array branch never consults it.
      expect(fieldErrors(failure([{ loc: ['name'], msg: 'required' }]))).toEqual({
        name: 'required',
      })
    })
  })

  describe('the array shape — parse_body forwarding Pydantic', () => {
    it('takes the field from loc and the wording from msg', () => {
      expect(
        fieldErrors(
          failure([
            {
              type: 'string_too_long',
              loc: ['smsNumber'],
              msg: 'String should have at most 32 characters',
              input: '+1555012345678901234567890123456789',
              ctx: { max_length: 32 },
            },
          ]),
        ),
      ).toEqual({ smsNumber: 'String should have at most 32 characters' })
    })

    it('never surfaces `input`, which is only the admin’s own typing echoed back', () => {
      const mapped = fieldErrors(
        failure([
          { type: 'string_pattern_mismatch', loc: ['shortcut'], msg: 'String should match pattern',
            input: 'not-a-shortcut', ctx: { pattern: '^/[a-z0-9_-]+$' } },
        ]),
      )
      expect(Object.values(mapped)).not.toContain('not-a-shortcut')
      expect(JSON.stringify(mapped)).not.toContain('not-a-shortcut')
    })

    it('reports every field, and keeps the first error for a field that fails twice', () => {
      expect(
        fieldErrors(
          failure([
            { loc: ['locale'], msg: 'String should have at least 1 character' },
            { loc: ['shortcut'], msg: 'String should match pattern' },
            { loc: ['locale'], msg: 'a later complaint about the same input' },
          ]),
        ),
      ).toEqual({
        locale: 'String should have at least 1 character',
        shortcut: 'String should match pattern',
      })
    })

    it('uses the last loc element, so a nested field lands on its own input', () => {
      expect(fieldErrors(failure([{ loc: ['settings', 'slaMinutes'], msg: 'Input should be greater than 0' }])))
        .toEqual({ slaMinutes: 'Input should be greater than 0' })
    })

    it('leaves out an error whose loc ends in an array index, rather than keying it by a number', () => {
      // A list field's nth element names no input on any form. The panel banner still carries the
      // top-level message, so the failure is reported — just not pinned to a box.
      expect(fieldErrors(failure([{ loc: ['tags', 0], msg: 'Input should be a valid string' }]))).toEqual({})
    })

    it('keeps the fields it can place when one entry in the same failure cannot be placed', () => {
      expect(
        fieldErrors(
          failure([
            { loc: ['tags', 2], msg: 'Input should be a valid string' },
            { loc: ['name'], msg: 'String should have at least 1 character' },
          ]),
        ),
      ).toEqual({ name: 'String should have at least 1 character' })
    })

    it('skips an entry with no msg and one with no loc', () => {
      expect(fieldErrors(failure([{ loc: ['name'] }, { msg: 'orphaned' }]))).toEqual({})
    })
  })

  describe('nothing to map', () => {
    it('is empty when the error carries no details', () => {
      expect(fieldErrors(failure(undefined, 'Shortcut /wifi is already in use'))).toEqual({})
    })

    it('is empty for a null or non-object details', () => {
      expect(fieldErrors(failure(null))).toEqual({})
      expect(fieldErrors(failure('something went wrong'))).toEqual({})
      expect(fieldErrors(failure([]))).toEqual({})
    })

    it('is empty for no error at all, or an error that is not an ApiError', () => {
      expect(fieldErrors(null)).toEqual({})
      expect(fieldErrors(undefined)).toEqual({})
      expect(fieldErrors(new Error('boom'))).toEqual({})
    })

    it('names a field no form has without disturbing the ones it does', () => {
      // `code` is rejected by extra="forbid" on PropertySettingsPatch but is read-only in the UI,
      // so nothing looks it up. It must not break the lookup of the fields that are on screen.
      const mapped = fieldErrors(
        failure([
          { loc: ['code'], msg: 'Extra inputs are not permitted' },
          { loc: ['currency'], msg: 'String should match pattern' },
        ]),
      )
      expect(mapped.currency).toBe('String should match pattern')
      expect(mapped.name).toBeUndefined()
    })
  })
})
