import { expect, test, type Page } from '@playwright/test'

const PASSWORD = 'Password123!'

async function signIn(page: Page, email: string) {
  await page.goto('/login')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(PASSWORD)
  await page.getByRole('button', { name: /sign in/i }).click()
  await expect(page).toHaveURL(/\/app\//)
}

test('two agents on one conversation each see the other within 2 seconds', async ({ browser }) => {
  const first = await browser.newContext()
  const second = await browser.newContext()
  const ava = await first.newPage()
  const marcus = await second.newPage()

  await signIn(ava, 'ava@hvh.test')
  await ava.goto('/app/inbox')
  // Any conversation will do — nothing below depends on which. The href is what makes it a
  // queue row: the nav's own links (/app/inbox, /app/board, …) come first in the DOM.
  await ava.locator('a[href^="/app/inbox/"]').first().click()
  await expect(ava).toHaveURL(/\/app\/inbox\/.+/)
  const url = ava.url()

  await signIn(marcus, 'marcus@hvh.test')
  await marcus.goto(url)

  // §11.1 #3: each sees the other. The expect timeout is 15s, so assert the 2s
  // requirement explicitly rather than leaning on the default.
  await expect(ava.getByText(/Marcus is (viewing|replying)/)).toBeVisible({ timeout: 2000 })
  await expect(marcus.getByText(/Ava is (viewing|replying)/)).toBeVisible({ timeout: 2000 })

  // Composing flips the verb for the other viewer.
  await marcus.getByRole('textbox').click()
  await expect(ava.getByText('Marcus is replying')).toBeVisible({ timeout: 3000 })

  // Leaving clears it. This is an IN-APP click, not a goto: the socket stays open, so the clear
  // has to come from the app's own `presence` frame with a null conversationId. A hard navigation
  // would drop the socket and let the server's disconnect handler do the work instead, which is a
  // different mechanism and would stay green even if the app never sent the frame.
  await marcus.getByRole('link', { name: 'Board' }).click()
  await expect(ava.getByText(/Marcus is/)).toHaveCount(0, { timeout: 3000 })

  await first.close()
  await second.close()
})
