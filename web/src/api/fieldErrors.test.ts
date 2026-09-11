import { describe, expect, it } from 'vitest'
import { ApiError } from './client'
import { fieldErrors } from './fieldErrors'

function failure(details: unknown, message = 'Invalid request body'): ApiError {
  return new ApiError(400, 'VALIDATION_FAILED', message, details)
}

describe('fieldErrors', () => {
  describe('the object shape — domain validators and patch_changes', () => {
    it('keys a reason code by the camelCase field the server named', () => {
      expect(fieldErrors(failure({ escalationMinutes: 'required' }))).toEqual({
        escalationMinutes: 'required',
      })
    })

    it('carries every field in one failure', () => {
      // update_settings can refuse several cleared fields at once.
      expect(fieldErrors(failure({ name: 'required', currency: 'required' }))).toEqual({
        name: 'required',
        currency: 'required',
      })
    })

    it('passes the reason code through verbatim, for the form to word', () => {
      // normalize_phone raises a code, not a sentence, and not the raw input.
      expect(fieldErrors(failure({ smsNumber: 'invalid_phone_number' }))).toEqual({
        smsNumber: 'invalid_phone_number',
      })
    })

    it('stringifies a non-string value rather than rendering [object Object]', () => {
      expect(fieldErrors(failure({ slaMinutes: 0 }))).toEqual({ slaMinutes: '0' })
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
