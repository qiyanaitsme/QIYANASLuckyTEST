from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup
import random
import string
from database import Database
from config import *

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
db = Database()

class GameStates(StatesGroup):
    waiting_for_password = State()
    waiting_for_bet = State()
    placing_bets = State()

async def on_startup(dp):
    await db.init()

def get_numbers_keyboard(password: str):
    keyboard = types.InlineKeyboardMarkup(row_width=6)
    buttons = []
    for number in NUMBERS:
        buttons.append(
            types.InlineKeyboardButton(
                str(number),
                callback_data=f"bet_{password}_{number}"
            )
        )
    for i in range(0, len(buttons), 6):
        keyboard.row(*buttons[i:i+6])
    keyboard.add(types.InlineKeyboardButton("✅ Готово", callback_data=f"ready_{password}"))
    return keyboard

@dp.message_handler(commands=['start'])
async def cmd_start(message: types.Message):
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🎲 Создать игру", callback_data="create_game"),
        types.InlineKeyboardButton("🎮 Присоединиться", callback_data="join_game")
    )
    
    if message.from_user.id == ADMIN_ID:
        keyboard.add(types.InlineKeyboardButton("👑 АДМИН", callback_data="admin_panel"))
    
    await message.answer(MESSAGES['welcome'], reply_markup=keyboard)
    await db.add_user(message.from_user.id, message.from_user.username)

@dp.callback_query_handler(lambda c: c.data == "admin_panel", user_id=ADMIN_ID)
async def admin_panel(callback_query: types.CallbackQuery):
    rooms = await db.get_all_rooms()
    if not rooms:
        await callback_query.message.answer("Нет активных комнат")
        return
        
    response = "🎮 Активные комнаты:\n\n"
    for room in rooms:
        response += f"🔑 Пароль: {room['password']}\n"
        response += f"👥 Игроков: {room['player_count']}\n"
        response += "---------------\n"
    
    await callback_query.message.answer(response)


@dp.callback_query_handler(lambda c: c.data in ["create_game", "join_game"], state="*")
async def handle_menu_choice(callback_query: types.CallbackQuery, state: FSMContext):
    await state.finish()
    if callback_query.data == "create_game":
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=PASSWORD_LENGTH))
        await db.create_room(password)
        await db.add_player_to_room(password, callback_query.from_user.id)
        await callback_query.message.answer(
            MESSAGES['room_created'].format(password),
            reply_markup=get_numbers_keyboard(password)
        )
        await GameStates.placing_bets.set()
    else:
        await callback_query.message.answer("Введите пароль комнаты:")
        await GameStates.waiting_for_password.set()

@dp.message_handler(state=GameStates.waiting_for_password)
async def process_join_password(message: types.Message, state: FSMContext):
    password = message.text
    players = await db.get_room_players(password)
    
    if not players:
        await message.answer("Комната не найдена!")
        await state.finish()
        return
        
    await db.add_player_to_room(password, message.from_user.id)
    await message.answer(
        MESSAGES['room_joined'],
        reply_markup=get_numbers_keyboard(password)
    )
    await GameStates.placing_bets.set()

@dp.callback_query_handler(lambda c: c.data.startswith('bet_'), state=GameStates.placing_bets)
async def process_bet(callback_query: types.CallbackQuery, state: FSMContext):
    _, password, number = callback_query.data.split('_')
    number = int(number)
    
    bet_count = await db.get_player_bet_count(password, callback_query.from_user.id)
    if bet_count >= 5:
        await callback_query.answer("Вы уже выбрали 5 чисел!")
        return
    
    current_sum = await db.get_player_bets_sum(password, callback_query.from_user.id)
    remaining = STARTING_BALANCE - current_sum
    
    if remaining <= 0:
        await callback_query.answer("У вас не осталось очков!")
        return
    
    has_bet = await db.check_number_bet(password, callback_query.from_user.id, number)
    if has_bet:
        await callback_query.answer("Вы уже сделали ставку на это число!")
        return
    
    await state.update_data(password=password, number=number)
    await callback_query.message.answer(f"Введите сумму ставки (доступно {remaining} очков):")
    await GameStates.waiting_for_bet.set()

@dp.message_handler(state=GameStates.waiting_for_bet)
async def process_bet_amount(message: types.Message, state: FSMContext):
    try:
        amount = int(message.text)
        
        if amount <= 0:
            await message.answer("Ставка должна быть больше нуля!")
            return
            
        data = await state.get_data()
        password = data['password']
        number = data['number']
        
        current_sum = await db.get_player_bets_sum(password, message.from_user.id)
        remaining = STARTING_BALANCE - current_sum
        
        if amount > remaining:
            await message.answer(MESSAGES['not_enough_points'].format(remaining))
            return
        
        await db.place_bet(password, message.from_user.id, number, amount)
        new_remaining = remaining - amount
        
        await message.answer(
            MESSAGES['bet_placed'].format(new_remaining),
            reply_markup=get_numbers_keyboard(password)
        )
        await GameStates.placing_bets.set()
        
    except ValueError:
        await message.answer("Пожалуйста, введите целое число!")

@dp.callback_query_handler(lambda c: c.data.startswith('ready_'), state=GameStates.placing_bets)
async def process_ready(callback_query: types.CallbackQuery):
    password = callback_query.data.split('_')[1]
    
    current_balance = await db.get_player_balance(callback_query.from_user.id)
    if current_balance <= 0:
        current_balance = STARTING_BALANCE
        await db.update_player_balance(callback_query.from_user.id, STARTING_BALANCE)
    
    current_sum = await db.get_player_bets_sum(password, callback_query.from_user.id)
    if current_sum < current_balance:
        remaining = current_balance - current_sum
        await callback_query.message.answer(
            f"Вы должны распределить все очки!\nОсталось распределить: {remaining} очков"
        )
        return
    
    players = await db.get_room_players(password)
    if len(players) < 2:
        await callback_query.message.answer(
            "Ожидаем второго игрока для начала игры..."
        )
        await db.set_player_ready(password, callback_query.from_user.id)
        return
        
    await db.set_player_ready(password, callback_query.from_user.id)
    await callback_query.message.answer("Вы готовы! Ожидаем готовности второго игрока...")
    
    if await db.are_all_players_ready(password):
        await start_game(password)

async def start_game(password: str):
    winning_numbers = random.sample(NUMBERS, 5)
    players = await db.get_room_players(password)
    bets = await db.get_room_bets(password)
    
    player_points = {player_id: 0 for player_id in players}
    for player_id, number, amount in bets:
        if number in winning_numbers:
            player_points[player_id] += amount
    
    for player_id, points in player_points.items():
        await db.set_player_balance(player_id, points)
    
    player_balances = {player_id: await db.get_player_balance(player_id) for player_id in players}
    
    unique_players = list(set(players))
    if len(unique_players) != 2:
        return
        
    player1_id, player2_id = unique_players
    
    if player_balances[player1_id] == player_balances[player2_id] == 0:
        result_message = (
            f"🎲 Результаты игры: {password}\n\n"
            f"НИЧЬЯ!\n\n"
            f"Игрок 1:\n"
            f"ID: {player1_id}\n"
            f"Username: @{(await bot.get_chat(player1_id)).username}\n"
            f"Баланс: 0\n\n"
            f"Игрок 2:\n"
            f"ID: {player2_id}\n"
            f"Username: @{(await bot.get_chat(player2_id)).username}\n"
            f"Баланс: 0\n\n"
            f"Выпавшие числа: {winning_numbers}"
        )
    else:
        if player_balances[player1_id] >= player_balances[player2_id]:
            winner_id, loser_id = player1_id, player2_id
        else:
            winner_id, loser_id = player2_id, player1_id
        
        winner = await bot.get_chat(winner_id)
        loser = await bot.get_chat(loser_id)
        
        result_message = (
            f"🎲 Результаты игры: {password}\n\n"
            f"Победитель:\n"
            f"ID: {winner_id}\n"
            f"Username: @{winner.username}\n"
            f"Баланс: {player_balances[winner_id]}\n\n"
            f"Проигравший:\n"
            f"ID: {loser_id}\n"
            f"Username: @{loser.username}\n"
            f"Баланс: {player_balances[loser_id]}\n\n"
            f"Выпавшие числа: {winning_numbers}"
        )

    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton("🎲 Создать игру", callback_data="create_game"),
        types.InlineKeyboardButton("🎮 Присоединиться", callback_data="join_game")
    )
    
    for player_id in players:
        state = dp.current_state(user=player_id)
        await state.finish()
        
        await bot.send_message(player_id, result_message)
        await bot.send_message(
            player_id, 
            "Игра окончена! Выберите действие:",
            reply_markup=keyboard
        )
    
    await bot.send_message(CHAT_ID, result_message)
    await db.close_room(password)

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)