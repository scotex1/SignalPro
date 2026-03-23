//+------------------------------------------------------------------+
//|                                          SignalPro_EA.mq4        |
//|                   SignalPro FX — MT4 Expert Advisor              |
//|                                                                  |
//| Kya karta hai:                                                   |
//|   1. SignalPro ke signals ko MT4 mein execute karta hai          |
//|   2. Automatically BUY/SELL orders place karta hai               |
//|   3. TP aur SL automatically set karta hai                       |
//|   4. Telegram webhook se signals read karta hai                  |
//+------------------------------------------------------------------+
#property copyright "SignalPro FX"
#property version   "1.0"
#property strict

// ─────────────────────────────────────────────────
// INPUT PARAMETERS — MT4 mein EA settings mein dikhe
// ─────────────────────────────────────────────────
input double   LotSize          = 0.1;    // Lot size per trade
input bool     AutoTrade        = false;  // Auto trade ON/OFF
input bool     AlertsOnly       = true;   // Sirf alerts, trade nahi
input int      MagicNumber      = 12345;  // EA ki pehchan
input double   MaxSpreadPips    = 3.0;    // Isse zyada spread pe mat kholo
input bool     UseFixedSL       = false;  // Fixed SL use karo
input double   FixedSLPips      = 30.0;   // Fixed SL pips
input bool     TrailingStop     = true;   // Trailing stop
input double   TrailPips        = 15.0;   // Trail distance

// Colors for chart arrows
color BuyArrowColor  = clrLime;
color SellArrowColor = clrRed;
color TPLineColor    = clrDodgerBlue;
color SLLineColor    = clrOrangeRed;

// ─────────────────────────────────────────────────
// GLOBAL VARIABLES
// ─────────────────────────────────────────────────
string gSignalFile  = "signalpro_signal.txt";  // Signal file path
int    gLastBarTime = 0;
double gLastSignalEntry = 0;
string gLastSignalDir   = "";

//+------------------------------------------------------------------+
//| EA Initialize                                                     |
//+------------------------------------------------------------------+
int OnInit()
{
    Print("SignalPro EA v1.0 started on ", Symbol());
    Comment("SignalPro FX EA\nLot: ", LotSize, " | Magic: ", MagicNumber,
            "\nAuto: ", AutoTrade ? "ON" : "OFF");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| Main tick function                                               |
//+------------------------------------------------------------------+
void OnTick()
{
    // Trailing stop manage karo
    if (AutoTrade && TrailingStop)
        ManageTrailingStop();

    // Sirf naya bar aane pe signal check karo
    if (Time[0] == gLastBarTime) return;
    gLastBarTime = Time[0];

    // Signal file se padhna (Python engine likhta hai yeh file)
    string signal_dir   = "";
    double signal_entry = 0, signal_tp1 = 0, signal_tp2 = 0, signal_sl = 0;
    int    signal_strength = 0;

    if (ReadSignalFile(signal_dir, signal_entry, signal_tp1, signal_sl, signal_strength))
    {
        // Duplicate signal check
        if (signal_entry == gLastSignalEntry && signal_dir == gLastSignalDir)
            return;

        gLastSignalEntry = signal_entry;
        gLastSignalDir   = signal_dir;

        double spread = (Ask - Bid) / Point;
        if (spread > MaxSpreadPips * 10)
        {
            Print("Signal ignore: spread too high = ", spread/10, " pips");
            return;
        }

        // Chart pe signal draw karo
        DrawSignalArrow(signal_dir, signal_entry, signal_tp1, signal_sl);

        // Alert
        string alert_msg = StringConcatenate(
            "SignalPro: ", Symbol(), " ", signal_dir,
            " | Entry: ", DoubleToStr(signal_entry, Digits),
            " | TP: ",    DoubleToStr(signal_tp1, Digits),
            " | SL: ",    DoubleToStr(signal_sl, Digits),
            " | Strength: ", signal_strength, "%"
        );
        Alert(alert_msg);
        SendNotification(alert_msg);  // Mobile pe push notification

        // Auto execute karo (agar enabled hai)
        if (AutoTrade && !AlertsOnly)
            ExecuteSignal(signal_dir, signal_entry, signal_tp1, signal_sl);
    }
}

//+------------------------------------------------------------------+
//| Signal file padhna — Python yeh file likhta hai                  |
//+------------------------------------------------------------------+
bool ReadSignalFile(string &direction, double &entry, double &tp,
                    double &sl, int &strength)
{
    int file = FileOpen(gSignalFile, FILE_READ | FILE_TXT | FILE_ANSI);
    if (file == INVALID_HANDLE) return false;

    string line = FileReadString(file);
    FileClose(file);

    // Format: "BUY,2318.50,2335.00,2305.00,78"
    string parts[];
    int count = StringSplit(line, ',', parts);
    if (count < 5) return false;

    direction = parts[0];
    entry     = StringToDouble(parts[1]);
    tp        = StringToDouble(parts[2]);
    sl        = StringToDouble(parts[3]);
    strength  = (int)StringToInteger(parts[4]);

    return (direction == "BUY" || direction == "SELL") && entry > 0;
}

//+------------------------------------------------------------------+
//| Trade execute karna                                              |
//+------------------------------------------------------------------+
void ExecuteSignal(string direction, double entry, double tp, double sl)
{
    // Existing trades check karo
    if (CountMyTrades() > 0)
    {
        Print("Trade already open, skipping new signal.");
        return;
    }

    int    cmd      = (direction == "BUY") ? OP_BUY : OP_SELL;
    double price    = (direction == "BUY") ? Ask : Bid;
    double my_sl    = UseFixedSL ? CalcFixedSL(direction) : sl;
    double my_tp    = tp;
    color  clr      = (direction == "BUY") ? BuyArrowColor : SellArrowColor;

    int ticket = OrderSend(Symbol(), cmd, LotSize, price, 3, my_sl, my_tp,
                           "SignalPro", MagicNumber, 0, clr);

    if (ticket > 0)
        Print("Order placed: ", direction, " Ticket=", ticket,
              " Entry=", price, " SL=", my_sl, " TP=", my_tp);
    else
        Print("Order FAILED: Error=", GetLastError());
}

//+------------------------------------------------------------------+
//| Trailing stop manage karna                                       |
//+------------------------------------------------------------------+
void ManageTrailingStop()
{
    for (int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if (!OrderSelect(i, SELECT_BY_POS, MODE_TRADES)) continue;
        if (OrderMagicNumber() != MagicNumber) continue;
        if (OrderSymbol() != Symbol()) continue;

        double trail_dist = TrailPips * Point * 10;

        if (OrderType() == OP_BUY)
        {
            double new_sl = Bid - trail_dist;
            if (new_sl > OrderStopLoss() + Point)
                OrderModify(OrderTicket(), OrderOpenPrice(), new_sl,
                            OrderTakeProfit(), 0, clrYellow);
        }
        else if (OrderType() == OP_SELL)
        {
            double new_sl = Ask + trail_dist;
            if (new_sl < OrderStopLoss() - Point || OrderStopLoss() == 0)
                OrderModify(OrderTicket(), OrderOpenPrice(), new_sl,
                            OrderTakeProfit(), 0, clrYellow);
        }
    }
}

//+------------------------------------------------------------------+
//| Chart pe arrows aur lines draw karna                            |
//+------------------------------------------------------------------+
void DrawSignalArrow(string direction, double entry, double tp, double sl)
{
    string prefix = "SP_" + TimeToStr(TimeCurrent(), TIME_DATE|TIME_MINUTES) + "_";

    // Arrow
    string arrow_name = prefix + "arrow";
    int arrow_code = (direction == "BUY") ? 233 : 234;
    color arrow_color = (direction == "BUY") ? BuyArrowColor : SellArrowColor;

    ObjectCreate(0, arrow_name, OBJ_ARROW, 0, Time[0], entry);
    ObjectSetInteger(0, arrow_name, OBJPROP_ARROWCODE, arrow_code);
    ObjectSetInteger(0, arrow_name, OBJPROP_COLOR, arrow_color);
    ObjectSetInteger(0, arrow_name, OBJPROP_WIDTH, 3);

    // TP line
    string tp_name = prefix + "tp";
    ObjectCreate(0, tp_name, OBJ_HLINE, 0, 0, tp);
    ObjectSetInteger(0, tp_name, OBJPROP_COLOR, TPLineColor);
    ObjectSetInteger(0, tp_name, OBJPROP_STYLE, STYLE_DOT);
    ObjectSetString(0, tp_name, OBJPROP_TEXT, "TP: " + DoubleToStr(tp, Digits));

    // SL line
    string sl_name = prefix + "sl";
    ObjectCreate(0, sl_name, OBJ_HLINE, 0, 0, sl);
    ObjectSetInteger(0, sl_name, OBJPROP_COLOR, SLLineColor);
    ObjectSetInteger(0, sl_name, OBJPROP_STYLE, STYLE_DOT);
    ObjectSetString(0, sl_name, OBJPROP_TEXT, "SL: " + DoubleToStr(sl, Digits));

    // Label
    string lbl_name = prefix + "label";
    ObjectCreate(0, lbl_name, OBJ_TEXT, 0, Time[0], entry);
    ObjectSetString(0, lbl_name, OBJPROP_TEXT,
                    "SignalPro " + direction + " | TP: " + DoubleToStr(tp, Digits));
    ObjectSetInteger(0, lbl_name, OBJPROP_COLOR, arrow_color);
    ObjectSetInteger(0, lbl_name, OBJPROP_FONTSIZE, 8);

    ChartRedraw();
}

//+------------------------------------------------------------------+
//| Fixed SL calculate karna                                        |
//+------------------------------------------------------------------+
double CalcFixedSL(string direction)
{
    double sl_dist = FixedSLPips * Point * 10;
    return (direction == "BUY") ? Ask - sl_dist : Bid + sl_dist;
}

//+------------------------------------------------------------------+
//| Mere trades count karna                                         |
//+------------------------------------------------------------------+
int CountMyTrades()
{
    int count = 0;
    for (int i = OrdersTotal() - 1; i >= 0; i--)
    {
        if (OrderSelect(i, SELECT_BY_POS, MODE_TRADES) &&
            OrderMagicNumber() == MagicNumber &&
            OrderSymbol() == Symbol())
            count++;
    }
    return count;
}

//+------------------------------------------------------------------+
//| EA stop                                                          |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    Comment("");
    ObjectsDeleteAll(0, "SP_");
    Print("SignalPro EA stopped.");
}
