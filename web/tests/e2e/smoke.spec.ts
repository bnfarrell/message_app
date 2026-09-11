import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'Password123!'
// Base 36, not the raw epoch: a bare Date.now() is a 13-digit run, and one that happens to
// pass Luhn is rewritten to **** **** **** nnnn by §9.1's card redaction on the way in — so
// roughly one run in ten the marker would not survive the round trip.
const MARKER = `e2e-${Date.now().toString(36)}`
const GUEST_TEXT = `The AC is broken ${MARKER}`

async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/\/app\//)
}

test('a guest text becomes a reply, a work order, and a closed loop', async ({ browser }) => {
  const guest = await browser.newContext()
  const agent = await browser.newContext()
  const engineer = await browser.newContext()
  const simulator = await guest.newPage()
  const agentPage = await agent.newPage()
  const engineerPage = await engineer.newPage()

  // The list pane and the thread are both on screen at desktop width, and a row's preview
  // carries the message body verbatim (140 chars) — so assert on the thread's own bubbles
  // rather than on page-wide text, which would match the row too.
  const bubble = agentPage.getByTestId('bubble')
  const bubbleRow = agentPage.getByTestId('bubble-row')

  // 1. The guest texts the hotel.
  await simulator.goto('/sim')
  await simulator.getByText('Sarah Chen').click()
  await expect(simulator.getByTestId('sms-in').first()).toBeVisible()
  await simulator.getByPlaceholder(/text as/i).fill(GUEST_TEXT)
  await simulator.getByRole('button', { name: /^send$/i }).click()
  await expect(simulator.getByTestId('sms-out').filter({ hasText: MARKER })).toBeVisible()

  // 2. The agent sees it and replies.
  await signIn(agentPage, 'ava@hvh.test')
  await agentPage.goto('/app/inbox')
  const row = agentPage.getByRole('link').filter({ hasText: MARKER })
  await expect(row).toBeVisible({ timeout: 20_000 })
  await row.click()
  await expect(bubble.filter({ hasText: GUEST_TEXT })).toBeVisible()

  const replyText = `Engineering is on the way ${MARKER}`
  await agentPage.getByRole('textbox').fill(replyText)
  await agentPage.getByRole('button', { name: /^send$/i }).click()

  // 3. The reply reaches delivered — the worker and the socket, end to end. Scoped to this
  // reply's own bubble: the seeded thread already holds delivered messages, so a page-wide
  // 'Delivered' would be green before the send ever happened.
  await expect(bubble.filter({ hasText: replyText })).toBeVisible()
  await expect(bubbleRow.filter({ hasText: replyText }).getByText('Delivered')).toBeVisible({
    timeout: 30_000,
  })
  await expect(simulator.getByTestId('sms-in').filter({ hasText: replyText })).toBeVisible({
    timeout: 30_000,
  })

  // 4. The agent raises a work order, pre-filled from the conversation.
  await agentPage.getByRole('button', { name: /create work order/i }).click()
  await expect(agentPage.getByLabel('Title')).not.toHaveValue('')
  const woTitle = `AC repair ${MARKER}`
  await agentPage.getByLabel('Title').fill(woTitle)
  await agentPage.getByRole('button', { name: /^create$/i }).click()
  await expect(agentPage.getByRole('link', { name: new RegExp(woTitle) })).toBeVisible()

  // 5. The engineer completes it.
  await signIn(engineerPage, 'eli@hvh.test')
  await engineerPage.goto('/app/board')
  await engineerPage.getByRole('link').filter({ hasText: woTitle }).click()
  await engineerPage.getByRole('button', { name: 'In progress' }).click()
  await expect(engineerPage.getByRole('button', { name: 'Complete' })).toBeVisible()
  await engineerPage.getByRole('button', { name: 'Complete' }).click()

  // 6. The agent gets the draft prompt without reloading, and sends it. Scoped to this run's
  // work order: a run that died between completing the WO and sending the draft leaves its
  // prompt pending on this conversation, and the next run must not trip over it.
  const banner = agentPage.getByTestId('draft-prompt').filter({ hasText: woTitle })
  await expect(banner).toBeVisible({ timeout: 30_000 })
  await expect(banner).toContainText(/is complete/i)
  await banner.getByRole('button', { name: /use draft/i }).click()
  await expect(agentPage.getByRole('textbox')).not.toHaveValue('')
  const draftText = await agentPage.getByRole('textbox').inputValue()
  await agentPage.getByRole('button', { name: /^send$/i }).click()

  // 7. The guest receives it, and the prompt is gone. The whole draft, not its opening words:
  // every run's draft starts "Hi Sarah — our team has taken care of", and only the work-order
  // title it quotes carries this run's marker.
  await expect(simulator.getByTestId('sms-in').filter({ hasText: draftText.trim() })).toBeVisible({
    timeout: 30_000,
  })
  await expect(banner).toHaveCount(0)

  await guest.close()
  await agent.close()
  await engineer.close()
})
